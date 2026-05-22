"""Server-Sent Events for FFmpeg installation progress."""

import asyncio
import json
import threading
import time
from typing import AsyncGenerator, Optional
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()

# Global install state (thread-safe)
_install_state: dict = {
    "event_type": "idle",
    "progress_percent": 0,
    "step": "",
    "mirror": None,
    "retry_count": 0,
    "error": None,
    "last_update": 0,
}
_state_lock = threading.Lock()


def update_install_state(
    event_type: str,
    progress: int = 0,
    step: str = "",
    mirror: Optional[str] = None,
    retry: int = 0,
    error: Optional[str] = None,
) -> None:
    """Called from installer (potentially in a BackgroundTask thread) to update state."""
    global _install_state
    with _state_lock:
        _install_state = {
            "event_type": event_type,
            "progress_percent": progress,
            "step": step,
            "mirror": mirror,
            "retry_count": retry,
            "error": error,
            "last_update": time.time(),
        }


def reset_install_state() -> None:
    global _install_state
    with _state_lock:
        _install_state = {
            "event_type": "idle",
            "progress_percent": 0,
            "step": "",
            "mirror": None,
            "retry_count": 0,
            "error": None,
            "last_update": time.time(),
        }


def get_install_state() -> dict:
    with _state_lock:
        return _install_state.copy()


async def _sse_generator(request: Request) -> AsyncGenerator[str, None]:
    last_sent = 0.0
    last_state: Optional[dict] = None
    try:
        while True:
            if await request.is_disconnected():
                break

            state = get_install_state()
            current_update = state["last_update"]
            state_changed = current_update > last_sent or state != last_state

            if state_changed:
                last_sent = current_update
                last_state = state.copy()
                payload = json.dumps(state)
                message = "data: " + payload + "\n\n"
                yield message

                # Stop if terminal state
                if state["event_type"] in ("complete", "failed", "cancelled"):
                    await asyncio.sleep(0.5)
                    break
            else:
                await asyncio.sleep(0.2)
                if time.time() - last_sent > 5:
                    yield ":keep-alive\n\n"
                    last_sent = time.time()

    except asyncio.CancelledError:
        raise
    except Exception:
        pass


@router.get("/install-progress")
async def install_progress_stream(request: Request):
    return StreamingResponse(
        _sse_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
