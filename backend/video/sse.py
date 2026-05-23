"""SSE progress stream for video generation."""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from video.engine.progress_broadcaster import VideoProgressBroadcaster

router = APIRouter()


@router.get("/{video_id}/progress")
async def video_progress_stream(video_id: int, request: Request):
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