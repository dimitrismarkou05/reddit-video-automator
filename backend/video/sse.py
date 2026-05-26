"""SSE progress stream for video generation with robust error handling."""

import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from video.engine.progress_broadcaster import VideoProgressBroadcaster

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/{video_id}/progress")
async def video_progress_stream(video_id: int, request: Request):
    """Stream video generation progress via SSE."""
    logger.debug(f"[VideoSSE] New progress stream for video_id={video_id}")

    broadcaster = VideoProgressBroadcaster(video_id)

    return StreamingResponse(
        broadcaster.stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
