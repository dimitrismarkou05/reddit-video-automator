"""Video job manager: singleton for tracking active jobs, queue, pause/resume/cancel."""

import asyncio
import logging
from typing import Dict, List, Optional
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
    subtitle_style = None
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
        self._queue_event = asyncio.Event()  # Signals when queue has items
        self._queue_processor_task: Optional[asyncio.Task] = None
        self._shutdown = False
        logger.info("[JobManager] Initialized")

    def _ensure_queue_processor(self) -> None:
        """Ensure the queue processor background task is running."""
        if self._queue_processor_task is None or self._queue_processor_task.done():
            self._queue_processor_task = asyncio.create_task(
                self._queue_processor_loop(),
                name="queue_processor"
            )
            logger.info("[JobManager] Queue processor started")

    async def _queue_processor_loop(self) -> None:
        """Background task that processes queued items when slots become available."""
        logger.info("[JobManager] Queue processor loop running")
        while not self._shutdown:
            try:
                # Wait for queued items
                if not self._queue:
                    try:
                        await asyncio.wait_for(self._queue_event.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        continue

                self._queue_event.clear()

                if self._shutdown:
                    break

                # Process queue
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
        async with self._lock:
            if not self._queue:
                return

            # Check if we can acquire a slot
            if self._semaphore.locked():
                return

            # Get next video_id from queue
            video_id = self._queue.pop(0)

            # Check if job still exists and is in queued state
            job = self.active_jobs.get(video_id)
            if not job or job.status not in ("queued",):
                # Skip this item and reprocess
                if self._queue:
                    self._queue_event.set()
                return

        # Start the job
        logger.info(f"[JobManager] Starting queued job video_id={video_id}")
        asyncio.create_task(self._start_job(video_id), name=f"job_{video_id}")

    async def _start_job(self, video_id: int) -> None:
        """Start a video generation job with semaphore acquisition."""
        job = self.active_jobs.get(video_id)
        if not job:
            logger.warning(f"[JobManager] Cannot start job {video_id}: not found")
            return

        try:
            # Acquire semaphore slot
            async with self._semaphore:
                job.status = "processing"

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
                        logger.info(f"[JobManager] Video {video_id} already in terminal state: {video_record.status}")
                        return

                    video_record.status = VideoStatus.PROCESSING.value
                    video_record.current_step = "preparing"
                    video_record.queue_position = None
                    db.commit()

                    logger.info(f"[JobManager] Running pipeline for video_id={video_id}")

                    # Run the pipeline
                    pipeline = VideoPipeline(db)

                    try:
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
                        logger.error(f"[JobManager] Pipeline error for video_id={video_id}: {pipeline_exc}")
                        # Error is already recorded in the pipeline

                finally:
                    db.close()
                    # Update queue positions for remaining items
                    await self._update_queue_positions()
                    # Trigger processing of next item
                    if self._queue:
                        self._queue_event.set()

        except asyncio.CancelledError:
            logger.info(f"[JobManager] Job {video_id} was cancelled")
            job.status = "cancelled"
            raise
        except Exception as e:
            logger.error(f"[JobManager] Job {video_id} error: {e}", exc_info=True)
            job.status = "failed"

    async def _update_queue_positions(self) -> None:
        """Update queue_position in DB for all queued items."""
        from core.database import SessionLocal
        from video.models import GeneratedVideo

        db = SessionLocal()
        try:
            async with self._lock:
                for i, vid in enumerate(self._queue):
                    try:
                        video = db.query(GeneratedVideo).filter(
                            GeneratedVideo.id == vid
                        ).first()
                        if video:
                            video.queue_position = i + 1
                    except Exception as e:
                        logger.warning(f"[JobManager] Error updating queue position for {vid}: {e}")
                db.commit()
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
        subtitle_style=None,
        generate_hashtags: bool = True,
    ) -> None:
        """Submit a video generation job."""
        # Check if already tracked
        if video_id in self.active_jobs:
            existing = self.active_jobs[video_id]
            if existing.status in ("processing", "queued"):
                logger.info(f"[JobManager] Job {video_id} already active (status={existing.status})")
                return
            # If failed/cancelled, allow retry by removing old state
            if existing.status in ("done", "failed", "cancelled"):
                logger.info(f"[JobManager] Retrying job {video_id}")
                del self.active_jobs[video_id]

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
        # Signal that queue has items
        self._queue_event.set()

        logger.info(f"[JobManager] Job {video_id} submitted for story {story_id}, queue_len={len(self._queue)}")

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

            # Cancel the pipeline if it's running
            try:
                from video.engine.pipeline import VideoPipeline
                # We can't easily get the pipeline instance, but the DB status change
                # will be picked up by check_cancelled in the pipeline
            except Exception:
                pass

        except Exception as e:
            logger.error(f"[JobManager] Error during cancel DB update: {e}")
        finally:
            db.close()

        # Cleanup temp files
        try:
            from video.engine.utils import cleanup_temp
            cleanup_temp(video_id)
        except Exception as e:
            logger.warning(f"[JobManager] Temp cleanup error during cancel: {e}")

        # Update queue positions
        asyncio.create_task(self._update_queue_positions())

        return True

    def pause(self, video_id: int) -> bool:
        """Pause a video generation job."""
        job = self.active_jobs.get(video_id)
        if job and job.status == "processing":
            job.status = "paused"
            if job.task and not job.task.done():
                job.task.cancel()

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
                db.commit()
        except Exception as e:
            logger.error(f"[JobManager] Error during pause: {e}")
        finally:
            db.close()

        return True

    def resume(self, video_id: int) -> bool:
        """Resume a paused video generation job."""
        job = self.active_jobs.get(video_id)

        from core.database import SessionLocal
        from video.models import GeneratedVideo, VideoStatus
        db = SessionLocal()
        try:
            video = db.query(GeneratedVideo).filter(
                GeneratedVideo.id == video_id
            ).first()

            if not video:
                return False

            # Reset status to queued
            video.status = VideoStatus.QUEUED.value
            video.is_paused = False
            video.resumed_at = datetime.now(timezone.utc)
            db.commit()

            # Re-submit the job with original parameters
            if job:
                self.submit(
                    video_id=video.id,
                    story_id=video.story_id,
                    include_updates=job.include_updates,
                    voice_id=job.voice_id,
                    background_source=job.background_source,
                    video_format=job.video_format,
                    subtitle_style=job.subtitle_style,
                    generate_hashtags=job.generate_hashtags,
                )
            else:
                # If no job state, submit with defaults
                self.submit(
                    video_id=video.id,
                    story_id=video.story_id,
                )
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

        # Cancel all active jobs
        for vid, job in list(self.active_jobs.items()):
            if job.task and not job.task.done():
                job.task.cancel()
            job.status = "paused"
            paused_ids.append(vid)

        return paused_ids

    def cleanup_job(self, video_id: int) -> None:
        """Fully clean up a job's tracking state."""
        logger.info(f"[JobManager] Cleaning up job {video_id}")

        # Remove from queue
        if video_id in self._queue:
            self._queue.remove(video_id)

        # Remove from active jobs
        if video_id in self.active_jobs:
            job = self.active_jobs[video_id]
            if job.task and not job.task.done():
                try:
                    job.task.cancel()
                except Exception:
                    pass
            del self.active_jobs[video_id]

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
        except Exception as e:
            logger.error(f"[JobManager] Cleanup DB error: {e}")
        finally:
            db.close()

        # Cleanup temp files
        try:
            from video.engine.utils import cleanup_temp
            cleanup_temp(video_id)
        except Exception as e:
            logger.warning(f"[JobManager] Temp cleanup error: {e}")


# Global instance
job_manager = VideoJobManager()
