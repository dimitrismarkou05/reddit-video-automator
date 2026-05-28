"""Video job manager: singleton for tracking active jobs, queue, pause/resume/cancel.

CRITICAL FIXES APPLIED:
- Added missing datetime imports
- Fixed asyncio.create_task in sync contexts (cancel/pause/cleanup)
- Set job.task when starting jobs
- Added comprehensive debug logging
- Fixed queue position updates in sync contexts
- Ensured proper cleanup of all state
- FIXED: subtitle_style is now a proper dataclass field
- FIXED: cancel properly removes job from active_jobs and queue
- FIXED: _start_job checks if job was cancelled before processing
- FIXED: queue processor starts reliably with proper event sequencing
- FIXED: pause no longer causes task CancelledError to overwrite status
- FIXED: queue processor loop always checks queue after waking up
- FIXED: use asyncio.Condition for reliable queue signaling
- FIXED (Issue 2): Resume reads parameters from DB if not in active_jobs
- FIXED (Issue 6): Queue progress updates with position message
- FIXED (Issue 8): Reliable queue wake-up with immediate notify
- FIXED (Issue 13): Preserve queue_position for paused jobs
- FIXED (Issue 14): _ensure_queue_processor now handles both sync and async contexts
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class JobState:
    video_id: int
    story_id: int
    task: Optional[asyncio.Task] = None
    status: str = "queued"
    progress_percent: int = 0
    current_step: str = "queued"
    # Store original parameters for retry/resume
    include_updates: bool = True
    voice_id: str = "default"
    background_source: str = ""
    video_format: str = "shorts"
    subtitle_style: Optional[Any] = None
    generate_hashtags: bool = True


class VideoJobManager:
    """Singleton job manager for video generation."""

    _instance: Optional["VideoJobManager"] = None

    # Semaphore: max 2 concurrent video generations globally
    MAX_CONCURRENT = 2

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._lock = asyncio.Lock()
        self.active_jobs: Dict[int, JobState] = {}  # video_id -> JobState
        self._queue: List[int] = []  # Ordered list of queued video_ids
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)
        self._queue_condition = asyncio.Condition(self._lock)  # FIXED: Use Condition for reliable signaling
        self._queue_processor_task: Optional[asyncio.Task] = None
        self._shutdown = False
        logger.info("[JobManager] Initialized")

    def _ensure_queue_processor(self) -> None:
        """Ensure the queue processor background task is running.
        
        CRITICAL FIX (Issue 14): This method may be called from either:
        - An async context (lifespan, async route) where get_running_loop() works
        - A sync context (sync FastAPI route in thread pool) where it doesn't
        
        We try get_running_loop() first, then fall back to get_event_loop().
        Starting the processor in app lifespan (async) ensures it's ready before
        any sync routes can call submit().
        """
        if self._queue_processor_task is None or self._queue_processor_task.done():
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # Not in an async context - try to get the event loop for this thread
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    pass
            
            if loop is not None:
                try:
                    self._queue_processor_task = loop.create_task(
                        self._queue_processor_loop(),
                        name="queue_processor"
                    )
                    logger.info("[JobManager] Queue processor started")
                except Exception as e:
                    logger.error(f"[JobManager] Failed to start queue processor: {e}")
            else:
                logger.error("[JobManager] No event loop available to start queue processor")

    async def _queue_processor_loop(self) -> None:
        """Background task that processes queued items when slots become available."""
        logger.info("[JobManager] Queue processor loop running")
        while not self._shutdown:
            try:
                async with self._queue_condition:
                    # CRITICAL FIX (Issue 8): Always check queue first, then wait if empty
                    while not self._queue and not self._shutdown:
                        try:
                            await asyncio.wait_for(self._queue_condition.wait(), timeout=5.0)
                        except asyncio.TimeoutError:
                            pass

                    if self._shutdown:
                        break

                    # Process queue items if available
                    if self._queue:
                        await self._process_queue()

            except asyncio.CancelledError:
                logger.info("[JobManager] Queue processor cancelled")
                break
            except Exception as e:
                logger.error(f"[JobManager] Queue processor error: {e}", exc_info=True)
                await asyncio.sleep(1)

        logger.info("[JobManager] Queue processor stopped")

    async def _process_queue(self) -> None:
        """Process the next queued item if a slot is available."""
        # Check if we can acquire a slot (non-blocking)
        if self._semaphore.locked():
            logger.debug("[JobManager] Semaphore locked, waiting for slot")
            return

        if not self._queue:
            return

        # Get next video_id from queue
        video_id = self._queue.pop(0)
        logger.info(f"[JobManager] Processing next queued item: video_id={video_id}")

        # Check if job still exists and is in queued state
        job = self.active_jobs.get(video_id)
        if not job or job.status != "queued":
            logger.warning(f"[JobManager] Skipping job {video_id}, status={job.status if job else 'missing'}")
            # Signal to process next item if queue not empty
            if self._queue:
                async with self._queue_condition:
                    self._queue_condition.notify()
            return

        # Start the job (outside lock to avoid blocking)
        logger.info(f"[JobManager] Starting queued job video_id={video_id}")
        task = asyncio.create_task(self._start_job(video_id), name=f"job_{video_id}")

        # Store the task reference
        job = self.active_jobs.get(video_id)
        if job:
            job.task = task
            logger.debug(f"[JobManager] Stored task for job {video_id}")

    async def _start_job(self, video_id: int) -> None:
        """Start a video generation job with semaphore acquisition."""
        job = self.active_jobs.get(video_id)
        if not job:
            logger.warning(f"[JobManager] Cannot start job {video_id}: not found")
            return

        # Check if job was cancelled before we even start
        if job.status == "cancelled":
            logger.info(f"[JobManager] Job {video_id} was cancelled before starting, skipping")
            self._cleanup_job_state(video_id)
            return

        try:
            # Acquire semaphore slot
            async with self._semaphore:
                # DOUBLE CHECK: job might have been cancelled while waiting for semaphore
                if job.status == "cancelled":
                    logger.info(f"[JobManager] Job {video_id} cancelled while waiting for semaphore")
                    self._cleanup_job_state(video_id)
                    return

                # TRIPLE CHECK: job might have been paused
                if job.status == "paused":
                    logger.info(f"[JobManager] Job {video_id} is paused, releasing semaphore")
                    return

                job.status = "processing"
                logger.info(f"[JobManager] Acquired semaphore slot for video_id={video_id}")

                from core.database import SessionLocal
                from video.models import GeneratedVideo, VideoStatus
                from video.engine.pipeline import VideoPipeline

                db = SessionLocal()
                try:
                    # Update DB status
                    video_record = db.query(GeneratedVideo).filter(
                        GeneratedVideo.id == video_id
                    ).first()

                    if not video_record:
                        logger.error(f"[JobManager] Video record {video_id} not found")
                        return

                    if video_record.status in (
                        VideoStatus.DONE.value,
                        VideoStatus.FAILED.value,
                        VideoStatus.CANCELLED.value,
                        VideoStatus.PAUSED.value,
                    ):
                        logger.info(f"[JobManager] Video {video_id} already in terminal/paused state: {video_record.status}")
                        return

                    video_record.status = VideoStatus.PROCESSING.value
                    video_record.current_step = "preparing"
                    video_record.queue_position = None
                    db.commit()
                    logger.info(f"[JobManager] DB status updated to PROCESSING for video_id={video_id}")

                    # Run the pipeline
                    pipeline = VideoPipeline(db)

                    try:
                        logger.info(f"[JobManager] Running pipeline for video_id={video_id}")
                        await pipeline.generate(
                            video_record=video_record,
                            include_updates=job.include_updates,
                            voice_id=job.voice_id,
                            background_source=job.background_source,
                            video_format=job.video_format,
                            subtitle_style=job.subtitle_style,
                            generate_hashtags=job.generate_hashtags,
                        )
                        logger.info(f"[JobManager] Pipeline completed for video_id={video_id}")
                    except Exception as pipeline_exc:
                        logger.error(f"[JobManager] Pipeline error for video_id={video_id}: {pipeline_exc}", exc_info=True)

                finally:
                    db.close()
                    # Update queue positions for remaining items
                    await self._update_queue_positions()
                    # Trigger processing of next item
                    async with self._queue_condition:
                        if self._queue:
                            self._queue_condition.notify()

        except asyncio.CancelledError:
            logger.info(f"[JobManager] Job {video_id} task was cancelled")
            # CRITICAL FIX: Check if this was a PAUSE or a real CANCEL
            current_job = self.active_jobs.get(video_id)
            if current_job:
                if current_job.status == "paused":
                    logger.info(f"[JobManager] Job {video_id} was paused, keeping state")
                    # Don't change status - it's already 'paused'
                else:
                    logger.info(f"[JobManager] Job {video_id} was cancelled, cleaning up")
                    current_job.status = "cancelled"
                    self._cleanup_job_state(video_id)
            raise
        except Exception as e:
            logger.error(f"[JobManager] Job {video_id} error: {e}", exc_info=True)
            job.status = "failed"
            # Clean up failed job state after a delay
            try:
                loop = asyncio.get_running_loop()
                loop.call_later(30, lambda: self._cleanup_job_state(video_id))
            except RuntimeError:
                pass

    def _cleanup_job_state(self, video_id: int) -> None:
        """Remove job from active_jobs and queue. Sync version for cleanup."""
        logger.info(f"[JobManager] Cleaning up state for job {video_id}")

        # Remove from queue if present
        if video_id in self._queue:
            self._queue.remove(video_id)
            logger.info(f"[JobManager] Removed {video_id} from queue")

        # Remove from active jobs
        if video_id in self.active_jobs:
            job = self.active_jobs[video_id]
            if job.task and not job.task.done():
                try:
                    job.task.cancel()
                except Exception:
                    pass
            del self.active_jobs[video_id]
            logger.info(f"[JobManager] Removed {video_id} from active_jobs")

        # Update queue positions asynchronously if possible
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                asyncio.create_task(self._update_queue_positions())
        except RuntimeError:
            pass

    async def _update_queue_positions(self) -> None:
        """Update queue_position in DB for all queued items."""
        from core.database import SessionLocal
        from video.models import GeneratedVideo

        db = SessionLocal()
        try:
            for i, vid in enumerate(self._queue):
                try:
                    video = db.query(GeneratedVideo).filter(
                        GeneratedVideo.id == vid
                    ).first()
                    if video:
                        video.queue_position = i + 1
                        # FIX 6: Update current_step with queue message
                        video.current_step = f"Waiting in queue... Position {i + 1}"
                        logger.debug(f"[JobManager] Updated queue position for {vid}: {i + 1}")
                except Exception as e:
                    logger.warning(f"[JobManager] Error updating queue position for {vid}: {e}")
            db.commit()
            logger.info(f"[JobManager] Updated queue positions for {len(self._queue)} items")
        except Exception as e:
            logger.error(f"[JobManager] Error updating queue positions: {e}")
        finally:
            db.close()

    def submit(
        self,
        video_id: int,
        story_id: int,
        include_updates: bool = True,
        voice_id: str = "default",
        background_source: str = "",
        video_format: str = "shorts",
        subtitle_style: Optional[Any] = None,
        generate_hashtags: bool = True,
    ) -> None:
        """Submit a video generation job."""

        # Check if already tracked and active
        if video_id in self.active_jobs:
            existing = self.active_jobs[video_id]
            if existing.status in ("processing", "queued"):
                logger.info(f"[JobManager] Job {video_id} already active (status={existing.status})")
                return
            # If failed/cancelled/done, clean up old state first
            if existing.status in ("done", "failed", "cancelled"):
                logger.info(f"[JobManager] Cleaning up old job {video_id} for retry (was {existing.status})")
                self._cleanup_job_state(video_id)

        # Also ensure not in queue
        if video_id in self._queue:
            self._queue.remove(video_id)

        # Create job state with all parameters preserved for resume
        job = JobState(
            video_id=video_id,
            story_id=story_id,
            include_updates=include_updates,
            voice_id=voice_id,
            background_source=background_source,
            video_format=video_format,
            subtitle_style=subtitle_style,
            generate_hashtags=generate_hashtags,
            status="queued",
        )
        self.active_jobs[video_id] = job

        # Add to queue
        self._queue.append(video_id)

        # Ensure queue processor is running
        self._ensure_queue_processor()

        # FIX 8: Signal that queue has items - use Condition for reliability
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                # Schedule the notify on the event loop immediately
                asyncio.create_task(self._notify_queue())
        except RuntimeError:
            pass

        logger.info(f"[JobManager] Job {video_id} submitted for story {story_id}, queue_len={len(self._queue)}")

    async def _notify_queue(self) -> None:
        """Async helper to notify the queue condition."""
        async with self._queue_condition:
            self._queue_condition.notify()

    def cancel(self, video_id: int) -> bool:
        """Cancel a video generation job."""
        logger.info(f"[JobManager] Cancelling job {video_id}")

        # Remove from queue if queued
        if video_id in self._queue:
            self._queue.remove(video_id)
            logger.info(f"[JobManager] Removed {video_id} from queue")

        job = self.active_jobs.get(video_id)
        if job:
            if job.task and not job.task.done():
                job.task.cancel()
                logger.info(f"[JobManager] Cancelled task for {video_id}")
            job.status = "cancelled"

            # Remove from active_jobs immediately so retry works
            del self.active_jobs[video_id]
            logger.info(f"[JobManager] Removed {video_id} from active_jobs")

        # Update DB
        from core.database import SessionLocal
        from video.models import GeneratedVideo, VideoStatus
        db = SessionLocal()
        try:
            video = db.query(GeneratedVideo).filter(
                GeneratedVideo.id == video_id
            ).first()
            if video and video.status not in (
                VideoStatus.DONE.value,
                VideoStatus.FAILED.value,
                VideoStatus.CANCELLED.value,
            ):
                video.status = VideoStatus.CANCELLED.value
                video.cancelled_at = datetime.now(timezone.utc)
                video.queue_position = None
                db.commit()
                logger.info(f"[JobManager] Updated DB status to CANCELLED for {video_id}")
        except Exception as e:
            logger.error(f"[JobManager] Error during cancel DB update: {e}")
        finally:
            db.close()

        # Cleanup temp files
        try:
            from video.engine.utils import cleanup_temp
            cleanup_temp(video_id)
            logger.info(f"[JobManager] Cleaned up temp files for {video_id}")
        except Exception as e:
            logger.warning(f"[JobManager] Temp cleanup error during cancel: {e}")

        # Update queue positions
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                asyncio.create_task(self._update_queue_positions())
        except RuntimeError:
            pass

        return True

    def pause(self, video_id: int) -> bool:
        """Pause a video generation job."""
        logger.info(f"[JobManager] Pausing job {video_id}")
        job = self.active_jobs.get(video_id)
        if job and job.status == "processing":
            job.status = "paused"
            if job.task and not job.task.done():
                job.task.cancel()
                logger.info(f"[JobManager] Cancelled task for pause {video_id}")
            # CRITICAL FIX (Issue 13): Keep job in active_jobs so resume can find it
            # Don't remove it! Also preserve queue_position in DB

        from core.database import SessionLocal
        from video.models import GeneratedVideo, VideoStatus
        db = SessionLocal()
        try:
            video = db.query(GeneratedVideo).filter(
                GeneratedVideo.id == video_id
            ).first()
            if video and video.status not in (
                VideoStatus.DONE.value,
                VideoStatus.FAILED.value,
                VideoStatus.CANCELLED.value,
            ):
                video.status = VideoStatus.PAUSED.value
                video.is_paused = True
                video.paused_at = datetime.now(timezone.utc)
                # FIX 13: Do NOT clear queue_position for paused jobs
                # Keep it so user knows position when resumed
                db.commit()
                logger.info(f"[JobManager] Updated DB status to PAUSED for {video_id}")
        except Exception as e:
            logger.error(f"[JobManager] Error during pause: {e}")
        finally:
            db.close()

        return True

    def resume(self, video_id: int) -> bool:
        """Resume a paused video generation job."""
        logger.info(f"[JobManager] Resuming job {video_id}")

        from core.database import SessionLocal
        from video.models import GeneratedVideo, VideoStatus
        db = SessionLocal()
        try:
            video = db.query(GeneratedVideo).filter(
                GeneratedVideo.id == video_id
            ).first()

            if not video:
                logger.warning(f"[JobManager] Video {video_id} not found for resume")
                return False

            # Reset status to queued
            video.status = VideoStatus.QUEUED.value
            video.is_paused = False
            video.resumed_at = datetime.now(timezone.utc)
            db.commit()
            logger.info(f"[JobManager] Updated DB status to QUEUED for resume {video_id}")

            # FIX 2: Get original job params - first try active_jobs, then fall back to DB
            old_job = None
            if video_id in self.active_jobs:
                old_job = self.active_jobs[video_id]
                # Remove old state
                del self.active_jobs[video_id]
            else:
                # After server restart, active_jobs is empty - read from DB record
                logger.info(f"[JobManager] No in-memory job for {video_id}, reading params from DB")
                from video.schemas import SubtitleStyle
                subtitle_style = None
                if video.subtitle_style:
                    try:
                        subtitle_style = SubtitleStyle(**video.subtitle_style)
                    except Exception:
                        subtitle_style = None

                old_job = JobState(
                    video_id=video.id,
                    story_id=video.story_id,
                    include_updates=getattr(video, "include_updates", True),
                    voice_id=getattr(video, "voice_id", "default"),
                    background_source=video.background_source or "",
                    video_format=video.format or "shorts",
                    subtitle_style=subtitle_style,
                    generate_hashtags=getattr(video, "generate_hashtags", True),
                )

            # Re-submit the job
            self.submit(
                video_id=video.id,
                story_id=video.story_id,
                include_updates=old_job.include_updates if old_job else True,
                voice_id=old_job.voice_id if old_job else "default",
                background_source=old_job.background_source if old_job else "",
                video_format=old_job.video_format if old_job else "shorts",
                subtitle_style=old_job.subtitle_style if old_job else None,
                generate_hashtags=old_job.generate_hashtags if old_job else True,
            )
            logger.info(f"[JobManager] Re-submitted job {video_id} for resume")
        except Exception as e:
            logger.error(f"[JobManager] Error during resume: {e}")
        finally:
            db.close()

        return True

    def is_job_active(self, video_id: int) -> bool:
        """Check if a job is currently tracked (active, paused, or queued)."""
        job = self.active_jobs.get(video_id)
        if not job:
            return False
        return job.status not in ("done", "failed", "cancelled")

    def get_job_status(self, video_id: int) -> Optional[dict]:
        """Get status of a job."""
        job = self.active_jobs.get(video_id)
        if not job:
            return None
        return {
            "video_id": job.video_id,
            "story_id": job.story_id,
            "status": job.status,
            "progress_percent": job.progress_percent,
            "current_step": job.current_step,
        }

    def queue_position(self, video_id: int) -> Optional[int]:
        """Get the queue position for a video."""
        if video_id in self._queue:
            return self._queue.index(video_id) + 1
        return None

    def shutdown_all(self) -> List[int]:
        """Cancel all active jobs and return list of paused video IDs."""
        logger.info("[JobManager] Shutting down all jobs")
        paused_ids = []

        # Cancel queue processor
        self._shutdown = True
        if self._queue_processor_task and not self._queue_processor_task.done():
            self._queue_processor_task.cancel()
            logger.info("[JobManager] Cancelled queue processor")

        # Cancel all active jobs
        for vid, job in list(self.active_jobs.items()):
            if job.task and not job.task.done():
                job.task.cancel()
                logger.info(f"[JobManager] Cancelled task for {vid}")
            job.status = "paused"
            paused_ids.append(vid)

        logger.info(f"[JobManager] Shut down complete, paused {len(paused_ids)} jobs")
        return paused_ids

    def cleanup_job(self, video_id: int) -> None:
        """Fully clean up a job's tracking state."""
        logger.info(f"[JobManager] Cleaning up job {video_id}")

        # Remove from queue
        if video_id in self._queue:
            self._queue.remove(video_id)
            logger.info(f"[JobManager] Removed {video_id} from queue during cleanup")

        # Remove from active jobs
        if video_id in self.active_jobs:
            job = self.active_jobs[video_id]
            if job.task and not job.task.done():
                try:
                    job.task.cancel()
                    logger.info(f"[JobManager] Cancelled task during cleanup for {video_id}")
                except Exception:
                    pass
            del self.active_jobs[video_id]
            logger.info(f"[JobManager] Removed {video_id} from active_jobs")

        # Update DB
        from core.database import SessionLocal
        from video.models import GeneratedVideo
        db = SessionLocal()
        try:
            video = db.query(GeneratedVideo).filter(
                GeneratedVideo.id == video_id
            ).first()
            if video:
                video.queue_position = None
                db.commit()
                logger.info(f"[JobManager] Cleared queue_position in DB for {video_id}")
        except Exception as e:
            logger.error(f"[JobManager] Cleanup DB error: {e}")
        finally:
            db.close()

        # Cleanup temp files
        try:
            from video.engine.utils import cleanup_temp
            cleanup_temp(video_id)
            logger.info(f"[JobManager] Cleaned up temp files for {video_id}")
        except Exception as e:
            logger.warning(f"[JobManager] Temp cleanup error: {e}")

        # Update queue positions
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                asyncio.create_task(self._update_queue_positions())
        except RuntimeError:
            pass


# Global instance
job_manager = VideoJobManager()