"""Video job manager: singleton for tracking active jobs, queue, pause/resume/cancel."""

import asyncio
import weakref
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field


@dataclass
class JobState:
    video_id: int
    story_id: int
    task: Optional[asyncio.Task] = None
    status: str = "queued"
    progress_percent: int = 0
    current_step: str = "queued"


class VideoJobManager:
    """Singleton job manager for video generation."""

    _instance: Optional["VideoJobManager"] = None
    _lock = asyncio.Lock()

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
        self.active_jobs: Dict[int, JobState] = {}  # video_id -> JobState
        self._queue: Dict[int, List[int]] = {}  # chain_root_id -> [video_id, ...]
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)
        self._chain_active: Dict[int, int] = {}  # chain_root_id -> active video_id
        self._cleanup_callbacks: List[callable] = []

    def _get_chain_root(self, story_id: int, db) -> int:
        """Get the chain root story ID for a given story."""
        from stories.models import Story
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            return story_id
        root = story
        while root.parent_story_id is not None:
            root = root.parent_story
        return root.id

    async def acquire_slot(self, video_id: int, story_id: int, db) -> bool:
        """Try to acquire a processing slot. Returns True if acquired, False if queued."""
        chain_root = self._get_chain_root(story_id, db)

        # Check if chain already has an active job
        if chain_root in self._chain_active:
            # Add to queue
            if chain_root not in self._queue:
                self._queue[chain_root] = []
            if video_id not in self._queue[chain_root]:
                self._queue[chain_root].append(video_id)

            # Update queue position in DB
            position = self._queue[chain_root].index(video_id) + 1
            from core.database import SessionLocal
            session = SessionLocal()
            try:
                from video.models import GeneratedVideo
                video = session.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
                if video:
                    video.queue_position = position
                    video.status = "queued"
                    session.commit()
            finally:
                session.close()
            return False

        # Acquire the global semaphore
        await self._semaphore.acquire()
        self._chain_active[chain_root] = video_id
        return True

    def release_slot(self, video_id: int, story_id: int, db) -> Optional[int]:
        """Release slot and return next queued video_id if any."""
        chain_root = self._get_chain_root(story_id, db)

        # Release semaphore
        try:
            self._semaphore.release()
        except ValueError:
            pass  # Already released

        # Remove from chain active
        if chain_root in self._chain_active:
            del self._chain_active[chain_root]

        # Clean up active job
        if video_id in self.active_jobs:
            del self.active_jobs[video_id]

        # Process queue for this chain
        if chain_root in self._queue and self._queue[chain_root]:
            # Remove completed video from queue
            if video_id in self._queue[chain_root]:
                self._queue[chain_root].remove(video_id)

            if self._queue[chain_root]:
                next_video_id = self._queue[chain_root].pop(0)
                # Update remaining queue positions
                self._update_queue_positions(chain_root)
                return next_video_id

            del self._queue[chain_root]

        # Also check if there are orphaned entries
        self._cleanup()
        return None

    def _update_queue_positions(self, chain_root: int) -> None:
        """Update queue_position in DB for all queued items in a chain."""
        from core.database import SessionLocal
        session = SessionLocal()
        try:
            from video.models import GeneratedVideo
            queued = self._queue.get(chain_root, [])
            for i, vid in enumerate(queued):
                video = session.query(GeneratedVideo).filter(GeneratedVideo.id == vid).first()
                if video:
                    video.queue_position = i + 1
            session.commit()
        finally:
            session.close()

    def register_job(self, video_id: int, story_id: int, task: asyncio.Task) -> None:
        """Register an active job."""
        self.active_jobs[video_id] = JobState(
            video_id=video_id,
            story_id=story_id,
            task=task,
            status="processing",
        )

    def pause_job(self, video_id: int) -> bool:
        """Pause a job. Returns True if job was found and paused."""
        if video_id not in self.active_jobs:
            return False
        job = self.active_jobs[video_id]
        job.status = "paused"
        return True

    def resume_job(self, video_id: int) -> bool:
        """Resume a paused job."""
        if video_id not in self.active_jobs:
            return False
        job = self.active_jobs[video_id]
        job.status = "processing"
        return True

    def cancel_job(self, video_id: int) -> bool:
        """Cancel a job and clean up."""
        if video_id not in self.active_jobs:
            return False
        job = self.active_jobs[video_id]
        if job.task and not job.task.done():
            job.task.cancel()
        job.status = "cancelled"
        return True

    def get_job_status(self, video_id: int) -> Optional[dict]:
        """Get status of a job."""
        if video_id not in self.active_jobs:
            return None
        job = self.active_jobs[video_id]
        return {
            "video_id": job.video_id,
            "story_id": job.story_id,
            "status": job.status,
            "progress_percent": job.progress_percent,
            "current_step": job.current_step,
        }

    def is_job_active(self, video_id: int) -> bool:
        """Check if a job is currently tracked (active, paused, or queued)."""
        return video_id in self.active_jobs

    def _cleanup(self) -> None:
        """Remove completed/cancelled jobs from tracking."""
        done = [vid for vid, job in self.active_jobs.items() if job.status in ("done", "failed", "cancelled")]
        for vid in done:
            del self.active_jobs[vid]

    async def process_queue(self, db) -> None:
        """Process any pending queued items. Called after a job finishes."""
        for chain_root, queued in list(self._queue.items()):
            if chain_root not in self._chain_active and queued:
                next_video_id = queued.pop(0)
                self._update_queue_positions(chain_root)
                # This will be picked up by the queue worker
                return next_video_id
        return None

    def shutdown_all(self) -> List[int]:
        """Cancel all active jobs and return list of paused video IDs."""
        paused_ids = []
        for vid, job in list(self.active_jobs.items()):
            if job.task and not job.task.done():
                job.task.cancel()
            job.status = "paused"
            paused_ids.append(vid)
        return paused_ids

    def add_cleanup_callback(self, callback: callable) -> None:
        self._cleanup_callbacks.append(callback)


# Global instance
job_manager = VideoJobManager()
