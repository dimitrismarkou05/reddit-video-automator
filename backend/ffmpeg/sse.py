"""Server-Sent Events for FFmpeg installation progress."""

import asyncio
import json
import time
from typing import AsyncGenerator, Optional
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()

# Global install state (thread-safe via GIL for simple dict ops)
_install_state: dict = {
    "event_type": "idle",
    "progress_percent": 0,
    "step": "",
    "mirror": None,
    "retry_count": 0,
    "error": None,
    "last_update": 0,
}


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
    _install_state = {
        "event_type": "idle",
        "progress_percent": 0,
        "step": "",
        "mirror": None,
        "retry_count": 0,
        "error": None,
        "last_update": 0,
    }


def get_install_state() -> dict:
    return _install_state.copy()


async def _sse_generator(request: Request) -> AsyncGenerator[str, None]:
    last_sent = 0.0
    try:
        while True:
            if await request.is_disconnected():
                break

            state = get_install_state()
            current_update = state["last_update"]

            # Only send if state changed or keep-alive needed
            if current_update > last_sent:
                last_sent = current_update
                message = f"event: {state['event_type']}\ndata: {json.dumps(state)}\n\n"
                yield message

                # Stop if complete/failed/cancelled
                if state["event_type"] in ("complete", "failed", "cancelled"):
                    break
            else:
                # Keep-alive every 5 seconds
                await asyncio.sleep(0.5)
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