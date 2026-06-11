"""VideoProgressBroadcaster: push-based SSE with DB fallback.

The pipeline publishes to progress_push after every DB commit.  This
broadcaster subscribes to the push channel so events arrive with
sub-second latency.  If no push event arrives within FALLBACK_POLL_SEC
(e.g. on reconnect) it falls back to reading the DB directly so
existing state is always visible to new connections.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

from fastapi import Request

from core.database import SessionLocal
from video.models import GeneratedVideo
import video.engine.progress_push as progress_push

logger = logging.getLogger(__name__)

FALLBACK_POLL_SEC = 2.0
KEEP_ALIVE_INTERVAL = 15.0

_STATUS_MESSAGES: dict[str, str] = {
    "preparing":            "Preparing script",
    "downloading_model":    "Loading voice model",
    "tts":                  "Starting voice synthesis",
    "tts_synthesizing":     "Generating voice",
    "tts_done":             "Voice ready",
    "transcribing":         "Transcribing audio",
    "transcribe_done":      "Transcription complete",
    "generating_subtitles": "Building subtitles",
    "subtitles_done":       "Subtitles ready",
    "selecting_background": "Selecting background",
    "compositing":          "Rendering video",
    "compositing_done":     "Video rendered",
    "generating_thumbnail": "Creating thumbnail",
    "done":                 "Complete",
    "failed":               "Generation failed",
    "cancelled":            "Cancelled",
    "paused":               "Paused",
}


class VideoProgressBroadcaster:
    """Async generator that streams SSE events for a single video."""

    def __init__(self, video_id: int):
        self.video_id = video_id
        self._closed = False

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _sync_get_progress(self) -> Optional[dict]:
        session = SessionLocal()
        try:
            video = session.query(GeneratedVideo).filter(
                GeneratedVideo.id == self.video_id
            ).first()
            if not video:
                return None
            return _build_payload(video)
        except Exception as exc:
            logger.error(f"[ProgressBroadcaster {self.video_id}] DB error: {exc}")
            return None
        finally:
            session.close()

    async def _get_progress_from_db(self) -> Optional[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_get_progress)

    # ------------------------------------------------------------------
    # SSE stream
    # ------------------------------------------------------------------

    async def stream(self, request: Request) -> AsyncGenerator[str, None]:
        terminal = {"done", "failed", "cancelled"}
        last_data: Optional[dict] = None
        last_keep_alive = asyncio.get_event_loop().time()
        event_count = 0

        q = progress_push.subscribe(self.video_id)
        logger.debug(f"[ProgressBroadcaster {self.video_id}] Stream started")

        try:
            # Emit current state immediately on connect so the UI has data right away.
            initial = await self._get_progress_from_db()
            if initial is None:
                yield _not_found_event(self.video_id)
                return
            last_data = initial.copy()
            yield f"event: progress\ndata: {json.dumps(initial)}\n\n"
            event_count += 1
            if initial["status"] in terminal:
                return

            while not self._closed:
                # Disconnect check.
                try:
                    if await request.is_disconnected():
                        break
                except Exception:
                    break

                # Wait for a push event; fall back to DB poll on timeout.
                try:
                    data = await asyncio.wait_for(q.get(), timeout=FALLBACK_POLL_SEC)
                except asyncio.TimeoutError:
                    data = await self._get_progress_from_db()

                if data is None:
                    yield _not_found_event(self.video_id)
                    break

                # Only emit when something meaningful changed.
                if _data_changed(last_data, data):
                    last_data = data.copy()
                    event_count += 1
                    yield f"event: progress\ndata: {json.dumps(data)}\n\n"
                    logger.debug(
                        f"[ProgressBroadcaster {self.video_id}] "
                        f"#{event_count} {data['status']} {data['progress_percent']}%"
                    )

                # Keep-alive comment.
                now = asyncio.get_event_loop().time()
                if now - last_keep_alive > KEEP_ALIVE_INTERVAL:
                    yield ":keep-alive\n\n"
                    last_keep_alive = now

                if data["status"] in terminal:
                    await asyncio.sleep(0.3)
                    break

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(f"[ProgressBroadcaster {self.video_id}] Stream error: {exc}")
        finally:
            self._closed = True
            progress_push.unsubscribe(self.video_id, q)
            logger.debug(
                f"[ProgressBroadcaster {self.video_id}] "
                f"Stream ended, total events: {event_count}"
            )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _build_payload(video: GeneratedVideo) -> dict:
    step = video.current_step or ""
    return {
        "video_id": video.id,
        "status": video.status,
        "progress_percent": video.progress_percent,
        "current_step": step,
        "status_message": _STATUS_MESSAGES.get(step, step),
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


def _not_found_event(video_id: int) -> str:
    payload = {
        "video_id": video_id,
        "status": "failed",
        "progress_percent": 0,
        "current_step": "not_found",
        "status_message": "Video not found",
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
    return f"event: progress\ndata: {json.dumps(payload)}\n\n"


def _data_changed(prev: Optional[dict], curr: dict) -> bool:
    if prev is None:
        return True
    return (
        curr["progress_percent"] != prev.get("progress_percent")
        or curr["status"] != prev.get("status")
        or curr["current_step"] != prev.get("current_step")
        or curr["status_message"] != prev.get("status_message")
        or curr.get("error_message") != prev.get("error_message")
        or curr.get("queue_position") != prev.get("queue_position")
    )
