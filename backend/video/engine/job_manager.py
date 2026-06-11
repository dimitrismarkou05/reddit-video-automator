"""Video job manager: singleton for tracking active jobs, queue, pause/resume/cancel.

Improvements over original:
- finally block in _start_job always cleans up active_jobs after pipeline completes.
- Startup recovery: processing rows with no live job are reset to queued.
- Watchdog task detects stalled jobs (no progress for N minutes) and fails them.
- DB-backed queue rebuild on startup (queued rows sorted by queued_at).
- last_progress_at timestamp on JobState for watchdog.
"""

import asyncio
import concurrent.futures
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from video.engine.pipeline import VideoPipeline

logger = logging.getLogger(__name__)

# Per-stage stall limits (minutes without a progress update before the job is
# considered hung and forcibly failed).
_STALL_LIMITS: dict[str, int] = {
    "downloading_model":     10,
    "tts_synthesizing":      15,
    "transcribing":          10,
    "generating_subtitles":  5,
    "compositing":           30,
    "generating_thumbnail":  5,
    "default":               8,
}
_WATCHDOG_INTERVAL = 120  # seconds between watchdog passes


@dataclass
class JobState:
    video_id: int
    story_id: int
    task: Optional[asyncio.Task] = None
    status: str = "queued"
    progress_percent: int = 0
    current_step: str = "queued"
    last_progress_at: Optional[datetime] = None
    include_updates: bool = True
    voice_id: str = "default"
    background_source: str = ""
    video_format: str = "shorts"
    subtitle_style: Optional[Any] = None
    generate_hashtags: bool = True
    pipeline: Optional["VideoPipeline"] = None


_CANCEL_WAIT_TIMEOUT = 5.0


class VideoJobManager:
    """Singleton job manager for video generation."""

    _instance: Optional["VideoJobManager"] = None
    MAX_CONCURRENT = 1

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
        self.active_jobs: Dict[int, JobState] = {}
        self._queue: List[int] = []
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)
        self._queue_condition = asyncio.Condition(self._lock)
        self._queue_processor_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._shutdown = False
        logger.info("[JobManager] Initialized")

    # ------------------------------------------------------------------
    # Queue processor
    # ------------------------------------------------------------------

    def _ensure_queue_processor(self) -> None:
        """Ensure the queue processor and watchdog background tasks are running."""
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                pass

        if loop is None:
            logger.error("[JobManager] No event loop available")
            return

        if self._queue_processor_task is None or self._queue_processor_task.done():
            try:
                self._queue_processor_task = loop.create_task(
                    self._queue_processor_loop(), name="queue_processor"
                )
                logger.info("[JobManager] Queue processor started")
            except Exception as exc:
                logger.error(f"[JobManager] Failed to start queue processor: {exc}")

        if self._watchdog_task is None or self._watchdog_task.done():
            try:
                self._watchdog_task = loop.create_task(
                    self._watchdog_loop(), name="job_watchdog"
                )
                logger.info("[JobManager] Watchdog started")
            except Exception as exc:
                logger.error(f"[JobManager] Failed to start watchdog: {exc}")

    async def _queue_processor_loop(self) -> None:
        logger.info("[JobManager] Queue processor loop running")
        while not self._shutdown:
            try:
                async with self._queue_condition:
                    while not self._queue and not self._shutdown:
                        try:
                            await asyncio.wait_for(
                                self._queue_condition.wait(), timeout=5.0
                            )
                        except asyncio.TimeoutError:
                            pass
                    if self._shutdown:
                        break
                    if self._queue:
                        await self._process_queue()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"[JobManager] Queue processor error: {exc}", exc_info=True)
                await asyncio.sleep(1)
        logger.info("[JobManager] Queue processor stopped")

    async def _process_queue(self) -> None:
        if self._semaphore.locked():
            return
        if not self._queue:
            return
        video_id = self._queue.pop(0)
        job = self.active_jobs.get(video_id)
        if not job or job.status != "queued":
            logger.warning(
                f"[JobManager] Skipping {video_id}, "
                f"status={job.status if job else 'missing'}"
            )
            if self._queue:
                async with self._queue_condition:
                    self._queue_condition.notify()
            return
        task = asyncio.create_task(self._start_job(video_id), name=f"job_{video_id}")
        if video_id in self.active_jobs:
            self.active_jobs[video_id].task = task

    # ------------------------------------------------------------------
    # Watchdog
    # ------------------------------------------------------------------

    async def _watchdog_loop(self) -> None:
        """Periodically check for stalled jobs and fail them."""
        logger.info("[JobManager] Watchdog loop running")
        while not self._shutdown:
            try:
                await asyncio.sleep(_WATCHDOG_INTERVAL)
                if not self._shutdown:
                    await self._check_stalled_jobs()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"[JobManager] Watchdog error: {exc}", exc_info=True)
        logger.info("[JobManager] Watchdog stopped")

    async def _check_stalled_jobs(self) -> None:
        now = datetime.now(timezone.utc)
        for video_id, job in list(self.active_jobs.items()):
            if job.status != "processing":
                continue
            if job.last_progress_at is None:
                continue
            stage = job.current_step or "default"
            limit_min = _STALL_LIMITS.get(stage, _STALL_LIMITS["default"])
            stall_since = (now - job.last_progress_at).total_seconds() / 60
            if stall_since >= limit_min:
                logger.warning(
                    f"[JobManager] Watchdog: job {video_id} stalled at "
                    f"'{stage}' for {stall_since:.1f} min (limit {limit_min}m)"
                )
                await self._fail_stalled_job(video_id)

    async def _fail_stalled_job(self, video_id: int) -> None:
        job = self.active_jobs.get(video_id)
        if not job:
            return
        logger.error(
            f"[JobManager] Forcibly failing stalled job {video_id} "
            f"at step '{job.current_step}'"
        )
        if job.task and not job.task.done():
            job.task.cancel()
        job.status = "failed"

        from core.database import SessionLocal
        from video.models import GeneratedVideo, VideoStatus
        from stories.models import Story, StoryStatus
        db = SessionLocal()
        try:
            video = db.query(GeneratedVideo).filter(
                GeneratedVideo.id == video_id
            ).first()
            if video and video.status not in (
                VideoStatus.DONE.value, VideoStatus.FAILED.value,
                VideoStatus.CANCELLED.value,
            ):
                video.status = VideoStatus.FAILED.value
                video.error_message = (
                    f"Job stalled at '{job.current_step}' and was automatically failed. "
                    "Please retry."
                )
                video.error_type = "StalledJob"
                video.error_step = job.current_step
                from video.engine.utils import cleanup_temp
                cleanup_temp(video_id)
                story = db.query(Story).filter(
                    Story.id == job.story_id
                ).first()
                if story:
                    story.status = StoryStatus.VIDEO_FAILED.value
                db.commit()
                import video.engine.progress_push as progress_push
                from video.engine.pipeline import _build_progress_payload
                progress_push.push_progress(
                    video_id, _build_progress_payload(video, video.current_step or "")
                )
        except Exception as exc:
            logger.error(f"[JobManager] Watchdog DB update error: {exc}")
        finally:
            db.close()

        self._cleanup_job_state(video_id)
        async with self._queue_condition:
            if self._queue:
                self._queue_condition.notify()

    # ------------------------------------------------------------------
    # Job execution
    # ------------------------------------------------------------------

    async def _start_job(self, video_id: int) -> None:
        job = self.active_jobs.get(video_id)
        if not job:
            logger.warning(f"[JobManager] Cannot start {video_id}: not found")
            return
        if job.status == "cancelled":
            self._cleanup_job_state(video_id)
            return

        try:
            async with self._semaphore:
                if job.status == "cancelled":
                    self._cleanup_job_state(video_id)
                    return
                if job.status == "paused":
                    return

                job.status = "processing"
                job.last_progress_at = datetime.now(timezone.utc)
                logger.info(f"[JobManager] Starting job {video_id}")

                from core.database import SessionLocal
                from video.models import GeneratedVideo, VideoStatus
                from video.engine.pipeline import VideoPipeline

                db = SessionLocal()
                try:
                    video_record = db.query(GeneratedVideo).filter(
                        GeneratedVideo.id == video_id
                    ).first()
                    if not video_record:
                        logger.error(f"[JobManager] Video {video_id} not found in DB")
                        return
                    if video_record.status in (
                        VideoStatus.DONE.value, VideoStatus.FAILED.value,
                        VideoStatus.CANCELLED.value, VideoStatus.PAUSED.value,
                    ):
                        logger.info(
                            f"[JobManager] Video {video_id} already terminal: "
                            f"{video_record.status}"
                        )
                        return

                    video_record.status = VideoStatus.PROCESSING.value
                    video_record.current_step = "preparing"
                    video_record.queue_position = None
                    db.commit()

                    pipeline = VideoPipeline(db)
                    job.pipeline = pipeline

                    # Reflect progress heartbeats into JobState so watchdog can see them.
                    def _sync_job_state(pct: int, step: str) -> None:
                        j = self.active_jobs.get(video_id)
                        if j:
                            j.progress_percent = pct
                            j.current_step = step
                            j.last_progress_at = datetime.now(timezone.utc)

                    try:
                        await pipeline.generate(
                            video_record=video_record,
                            include_updates=job.include_updates,
                            voice_id=job.voice_id,
                            background_source=job.background_source,
                            video_format=job.video_format,
                            subtitle_style=job.subtitle_style,
                            generate_hashtags=job.generate_hashtags,
                            progress_callback=_sync_job_state,
                        )
                        logger.info(f"[JobManager] Pipeline completed for {video_id}")
                    except Exception as pipeline_exc:
                        logger.error(
                            f"[JobManager] Pipeline error for {video_id}: {pipeline_exc}",
                            exc_info=True,
                        )
                    finally:
                        job.pipeline = None
                finally:
                    db.close()
                    # Always update queue positions and signal next job.
                    await self._update_queue_positions()
                    async with self._queue_condition:
                        if self._queue:
                            self._queue_condition.notify()

        except asyncio.CancelledError:
            current_job = self.active_jobs.get(video_id)
            if current_job and current_job.status == "paused":
                logger.info(f"[JobManager] Job {video_id} paused")
            else:
                logger.info(f"[JobManager] Job {video_id} cancelled")
                if current_job:
                    current_job.status = "cancelled"
            raise
        except Exception as exc:
            logger.error(f"[JobManager] Job {video_id} error: {exc}", exc_info=True)
            j = self.active_jobs.get(video_id)
            if j:
                j.status = "failed"
        finally:
            # Always clean up on completion/failure (not on pause).
            j = self.active_jobs.get(video_id)
            if j and j.status not in ("paused",):
                self._cleanup_job_state(video_id)

    # ------------------------------------------------------------------
    # Queue positions
    # ------------------------------------------------------------------

    def _cleanup_job_state(self, video_id: int) -> None:
        if video_id in self._queue:
            self._queue.remove(video_id)
        if video_id in self.active_jobs:
            job = self.active_jobs[video_id]
            if job.task and not job.task.done():
                try:
                    job.task.cancel()
                except Exception:
                    pass
            del self.active_jobs[video_id]
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                asyncio.create_task(self._update_queue_positions())
        except RuntimeError:
            pass

    async def _update_queue_positions(self) -> None:
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
                        video.current_step = f"Waiting in queue… Position {i + 1}"
                except Exception as exc:
                    logger.warning(
                        f"[JobManager] Error updating queue position for {vid}: {exc}"
                    )
            db.commit()
        except Exception as exc:
            logger.error(f"[JobManager] Error updating queue positions: {exc}")
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
        if video_id in self.active_jobs:
            existing = self.active_jobs[video_id]
            if existing.status in ("processing", "queued"):
                return
            if existing.status in ("done", "failed", "cancelled"):
                self._cleanup_job_state(video_id)

        if video_id in self._queue:
            self._queue.remove(video_id)

        # Stamp queued_at on the DB record so the DB queue survives restarts.
        from core.database import SessionLocal
        from video.models import GeneratedVideo
        db = SessionLocal()
        try:
            video = db.query(GeneratedVideo).filter(
                GeneratedVideo.id == video_id
            ).first()
            if video and not video.queued_at:
                video.queued_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as exc:
            logger.warning(f"[JobManager] Could not stamp queued_at: {exc}")
        finally:
            db.close()

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
            last_progress_at=datetime.now(timezone.utc),
        )
        self.active_jobs[video_id] = job
        self._queue.append(video_id)
        self._ensure_queue_processor()

        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                asyncio.create_task(self._notify_queue())
        except RuntimeError:
            pass

        logger.info(
            f"[JobManager] Job {video_id} submitted, queue_len={len(self._queue)}"
        )

    async def _notify_queue(self) -> None:
        async with self._queue_condition:
            self._queue_condition.notify()

    async def _wait_for_task_done(
        self, task: asyncio.Task, timeout: float = _CANCEL_WAIT_TIMEOUT
    ) -> None:
        if task.done():
            return
        try:
            await asyncio.wait_for(task, timeout=timeout)
        except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
            pass

    def _wait_task_on_loop(self, task: asyncio.Task) -> None:
        if task.done():
            return
        try:
            loop = task.get_loop()
        except Exception:
            return
        if not loop.is_running():
            return
        fut = asyncio.run_coroutine_threadsafe(
            self._wait_for_task_done(task), loop
        )
        try:
            fut.result(timeout=_CANCEL_WAIT_TIMEOUT + 1)
        except concurrent.futures.TimeoutError:
            logger.warning(
                f"[JobManager] Timeout waiting for task {task.get_name()} to stop"
            )

    def cancel(self, video_id: int) -> bool:
        had_active_job = False

        if video_id in self._queue:
            self._queue.remove(video_id)

        job = self.active_jobs.get(video_id)
        if job:
            had_active_job = True
            if job.pipeline:
                try:
                    job.pipeline.cancel()
                except Exception as exc:
                    logger.warning(
                        f"[JobManager] Pipeline cancel error for {video_id}: {exc}"
                    )
            if job.task and not job.task.done():
                job.task.cancel()
                self._wait_task_on_loop(job.task)
            job.status = "cancelled"
            job.pipeline = None
            # Job may already be removed by _start_job finally / _cleanup_job_state
            self.active_jobs.pop(video_id, None)

        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                asyncio.create_task(self._update_queue_positions())
        except RuntimeError:
            pass

        logger.info(
            f"[JobManager] Cancelled video {video_id} "
            f"(had_active_job={had_active_job})"
        )
        return had_active_job

    def pause(self, video_id: int) -> bool:
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
                VideoStatus.DONE.value, VideoStatus.FAILED.value,
                VideoStatus.CANCELLED.value,
            ):
                video.status = VideoStatus.PAUSED.value
                video.is_paused = True
                video.paused_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as exc:
            logger.error(f"[JobManager] Pause DB error: {exc}")
        finally:
            db.close()
        return True

    def resume(self, video_id: int) -> bool:
        from core.database import SessionLocal
        from video.models import GeneratedVideo, VideoStatus
        db = SessionLocal()
        try:
            video = db.query(GeneratedVideo).filter(
                GeneratedVideo.id == video_id
            ).first()
            if not video:
                return False

            video.status = VideoStatus.QUEUED.value
            video.is_paused = False
            video.resumed_at = datetime.now(timezone.utc)
            db.commit()

            old_job = self.active_jobs.pop(video_id, None)
            if old_job is None:
                from video.schemas import SubtitleStyle
                subtitle_style = None
                if video.subtitle_style:
                    try:
                        subtitle_style = SubtitleStyle(**video.subtitle_style)
                    except Exception:
                        pass
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

            self.submit(
                video_id=video.id,
                story_id=video.story_id,
                include_updates=old_job.include_updates,
                voice_id=old_job.voice_id,
                background_source=old_job.background_source,
                video_format=old_job.video_format,
                subtitle_style=old_job.subtitle_style,
                generate_hashtags=old_job.generate_hashtags,
            )
            logger.info(f"[JobManager] Re-submitted {video_id} for resume")
        except Exception as exc:
            logger.error(f"[JobManager] Resume error: {exc}")
        finally:
            db.close()
        return True

    def rebuild_queue_from_db(self) -> int:
        """Load all 'queued' rows from DB and add them to the in-memory queue.

        Called once at startup to restore queued jobs that survived a restart.
        Returns the number of jobs re-queued.
        """
        from core.database import SessionLocal
        from video.models import GeneratedVideo, VideoStatus
        db = SessionLocal()
        count = 0
        try:
            rows = (
                db.query(GeneratedVideo)
                .filter(GeneratedVideo.status == VideoStatus.QUEUED.value)
                .order_by(
                    GeneratedVideo.queued_at.nullslast(),
                    GeneratedVideo.created_at,
                )
                .all()
            )
            for video in rows:
                if video.id not in self.active_jobs and video.id not in self._queue:
                    from video.schemas import SubtitleStyle
                    subtitle_style = None
                    if video.subtitle_style:
                        try:
                            subtitle_style = SubtitleStyle(**video.subtitle_style)
                        except Exception:
                            pass
                    job = JobState(
                        video_id=video.id,
                        story_id=video.story_id,
                        include_updates=getattr(video, "include_updates", True),
                        voice_id=getattr(video, "voice_id", "default"),
                        background_source=video.background_source or "",
                        video_format=video.format or "shorts",
                        subtitle_style=subtitle_style,
                        generate_hashtags=getattr(video, "generate_hashtags", True),
                        status="queued",
                        last_progress_at=datetime.now(timezone.utc),
                    )
                    self.active_jobs[video.id] = job
                    self._queue.append(video.id)
                    count += 1
            if count:
                logger.info(f"[JobManager] Rebuilt queue with {count} persisted job(s)")
        except Exception as exc:
            logger.error(f"[JobManager] Queue rebuild error: {exc}")
        finally:
            db.close()
        return count

    def is_job_active(self, video_id: int) -> bool:
        job = self.active_jobs.get(video_id)
        return bool(job and job.status not in ("done", "failed", "cancelled"))

    def get_job_status(self, video_id: int) -> Optional[dict]:
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
        if video_id in self._queue:
            return self._queue.index(video_id) + 1
        return None

    def shutdown_all(self) -> List[int]:
        logger.info("[JobManager] Shutting down all jobs")
        paused_ids = []
        self._shutdown = True

        for task in (self._queue_processor_task, self._watchdog_task):
            if task and not task.done():
                task.cancel()

        for vid, job in list(self.active_jobs.items()):
            if job.task and not job.task.done():
                job.task.cancel()
            job.status = "paused"
            paused_ids.append(vid)

        return paused_ids

    def cleanup_job(self, video_id: int) -> None:
        if video_id in self._queue:
            self._queue.remove(video_id)
        if video_id in self.active_jobs:
            job = self.active_jobs[video_id]
            if job.task and not job.task.done():
                try:
                    job.task.cancel()
                except Exception:
                    pass
            del self.active_jobs[video_id]

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
        except Exception as exc:
            logger.error(f"[JobManager] Cleanup DB error: {exc}")
        finally:
            db.close()

        try:
            from video.engine.utils import cleanup_temp
            cleanup_temp(video_id)
        except Exception as exc:
            logger.warning(f"[JobManager] Temp cleanup error: {exc}")

        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                asyncio.create_task(self._update_queue_positions())
        except RuntimeError:
            pass


job_manager = VideoJobManager()
