"""SSE progress stream for video generation."""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from notifications.sse import notification_queue, sse_generator
from core.database import SessionLocal
from video.engine.pipeline import VideoPipeline

router = APIRouter()


@router.get("/progress/{video_id}")
async def progress_stream(video_id: int, request: Request):
    queue = await notification_queue.connect()
    try:
        db = SessionLocal()
        try:
            pipeline = VideoPipeline(db)
            progress = pipeline.get_progress(video_id)
            await queue.put(f"event: progress\ndata: {progress}\n\n")
        finally:
            db.close()
    except Exception:
        pass

    return StreamingResponse(
        sse_generator(request, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
