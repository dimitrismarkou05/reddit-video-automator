"""VideoProgressBroadcaster: polls DB every 2s and streams SSE events."""

import asyncio
import json
from typing import AsyncGenerator, Optional

from sqlalchemy.orm import Session
from fastapi import Request

from core.database import SessionLocal
from video.models import GeneratedVideo


class VideoProgressBroadcaster:
    """Async generator that polls DB for video progress and yields SSE events."""

    POLL_INTERVAL = 2.0  # seconds

    def __init__(self, video_id: int):
        self.video_id = video_id

    async def _get_progress(self) -> Optional[dict]:
        """Fetch current progress from DB."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_get_progress)

    def _sync_get_progress(self) -> Optional[dict]:
        session = SessionLocal()
        try:
            video = session.query(GeneratedVideo).filter(
                GeneratedVideo.id == self.video_id
            ).first()
            if not video:
                return None
            return {
                "video_id": video.id,
                "status": video.status,
                "progress_percent": video.progress_percent,
                "current_step": video.current_step,
                "step_progress": video.step_progress,
                "error_message": video.error_message,
                "error_type": video.error_type,
                "error_step": video.error_step,
                "queue_position": video.queue_position,
                "is_paused": video.is_paused,
                "retry_count": video.retry_count,
                "thumbnail_path": video.thumbnail_path,
                "video_path": video.video_path,
            }
        finally:
            session.close()

    async def stream(self, request: Request) -> AsyncGenerator[str, None]:
        """Stream progress events until terminal state."""
        terminal_states = {"done", "failed", "cancelled"}
        last_data = None

        try:
            while True:
                if await request.is_disconnected():
                    break

                data = await self._get_progress()
                if data is None:
                    # Video deleted / not found – send a synthetic terminal event so the UI dies gracefully
                    payload = {
                        "video_id": self.video_id,
                        "status": "failed",
                        "progress_percent": 0,
                        "current_step": "failed",
                        "step_progress": 0,
                        "error_message": "Video not found",
                        "error_type": "NotFound",
                        "error_step": "lookup",
                        "queue_position": None,
                        "is_paused": False,
                        "retry_count": 0,
                        "thumbnail_path": None,
                        "video_path": None,
                    }
                    yield f"event: progress\ndata: {json.dumps(payload)}\n\n"
                    break

                # Only send if data changed
                if data != last_data:
                    last_data = data.copy()
                    yield f"event: progress\ndata: {json.dumps(data)}\n\n"

                if data["status"] in terminal_states:
                    # Keep connection open a moment so the client receives the final frame,
                    # then close. The client is responsible for calling .close().
                    await asyncio.sleep(0.5)
                    break

                await asyncio.sleep(self.POLL_INTERVAL)

        except asyncio.CancelledError:
            raise
        except Exception:
            pass