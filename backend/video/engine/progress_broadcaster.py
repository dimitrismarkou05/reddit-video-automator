"""VideoProgressBroadcaster: polls DB every 1.5s and streams SSE events with proper cleanup.

FIXES:
- Better error handling
- Proper terminal state detection
- Enhanced logging
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

from sqlalchemy.orm import Session
from fastapi import Request

from core.database import SessionLocal
from video.models import GeneratedVideo

logger = logging.getLogger(__name__)


class VideoProgressBroadcaster:
    """Async generator that polls DB for video progress and yields SSE events."""

    POLL_INTERVAL = 1.5  # seconds - slightly faster for more responsive UI
    KEEP_ALIVE_INTERVAL = 15.0  # seconds

    def __init__(self, video_id: int):
        self.video_id = video_id
        self._closed = False

    async def _get_progress(self) -> Optional[dict]:
        """Fetch current progress from DB in a thread-safe way."""
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
        except Exception as e:
            logger.error(f"[ProgressBroadcaster {self.video_id}] DB error: {e}")
            return None
        finally:
            session.close()

    async def stream(self, request: Request) -> AsyncGenerator[str, None]:
        """Stream progress events until terminal state with proper cleanup."""
        terminal_states = {"done", "failed", "cancelled"}
        last_data = None
        last_keep_alive = asyncio.get_event_loop().time()
        event_count = 0

        logger.debug(f"[ProgressBroadcaster {self.video_id}] Stream started")

        try:
            while not self._closed:
                # Check if client disconnected
                try:
                    if await request.is_disconnected():
                        logger.debug(f"[ProgressBroadcaster {self.video_id}] Client disconnected")
                        break
                except Exception as e:
                    logger.debug(f"[ProgressBroadcaster {self.video_id}] Disconnect check error: {e}")
                    break

                # Get progress from DB
                try:
                    data = await self._get_progress()
                except Exception as e:
                    logger.error(f"[ProgressBroadcaster {self.video_id}] Error fetching progress: {e}")
                    data = None

                if data is None:
                    # Video deleted / not found – send terminal event
                    payload = {
                        "video_id": self.video_id,
                        "status": "failed",
                        "progress_percent": 0,
                        "current_step": "not_found",
                        "step_progress": 0,
                        "error_message": "Video record not found",
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

                # Send if data changed
                if data != last_data:
                    try:
                        last_data = data.copy()
                        event_count += 1
                        yield f"event: progress\ndata: {json.dumps(data)}\n\n"
                        logger.debug(f"[ProgressBroadcaster {self.video_id}] Event #{event_count} sent: {data['status']} {data['progress_percent']}%")
                    except Exception as e:
                        logger.debug(f"[ProgressBroadcaster {self.video_id}] Yield error: {e}")
                        break

                # Send keep-alive periodically
                now = asyncio.get_event_loop().time()
                if now - last_keep_alive > self.KEEP_ALIVE_INTERVAL:
                    yield ":keep-alive\n\n"
                    last_keep_alive = now

                # Check terminal state
                if data["status"] in terminal_states:
                    logger.info(f"[ProgressBroadcaster {self.video_id}] Terminal state reached: {data['status']}, total events: {event_count}")
                    # Send one final update, wait, then close
                    await asyncio.sleep(0.5)
                    break

                # Wait before next poll
                try:
                    await asyncio.sleep(self.POLL_INTERVAL)
                except asyncio.CancelledError:
                    logger.debug(f"[ProgressBroadcaster {self.video_id}] Sleep cancelled")
                    break

        except asyncio.CancelledError:
            logger.debug(f"[ProgressBroadcaster {self.video_id}] Stream cancelled")
        except Exception as e:
            logger.error(f"[ProgressBroadcaster {self.video_id}] Stream error: {e}")
        finally:
            self._closed = True
            logger.debug(f"[ProgressBroadcaster {self.video_id}] Stream ended, total events: {event_count}")
