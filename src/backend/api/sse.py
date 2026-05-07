"""Server-Sent Events for real-time notifications and progress updates."""

import asyncio
import json
from typing import AsyncGenerator
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()

class SSEQueue:
    def __init__(self):
        self._queues = []

    async def connect(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self._queues.append(queue)
        return queue

    def disconnect(self, queue: asyncio.Queue):
        if queue in self._queues:
            self._queues.remove(queue)

    async def broadcast(self, event_type: str, data: dict):
        message = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        dead_queues = []
        for queue in self._queues:
            try:
                await queue.put(message)
            except Exception:
                dead_queues.append(queue)
        for dq in dead_queues:
            self.disconnect(dq)

notification_queue = SSEQueue()

async def sse_generator(request: Request, queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield message
            except asyncio.TimeoutError:
                yield ":keep-alive\n\n"
    except Exception:
        pass
    finally:
        notification_queue.disconnect(queue)

@router.get("/sse/notifications")
async def notifications_stream(request: Request):
    queue = await notification_queue.connect()
    return StreamingResponse(
        sse_generator(request, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@router.get("/sse/progress/{video_id}")
async def progress_stream(video_id: int, request: Request):
    queue = await notification_queue.connect()
    from backend.video.pipeline import VideoPipeline
    from backend.database import SessionLocal
    db = SessionLocal()
    try:
        pipeline = VideoPipeline(db)
        progress = pipeline.get_progress(video_id)
        await queue.put(f"event: progress\ndata: {json.dumps(progress)}\n\n")
    finally:
        db.close()

    return StreamingResponse(
        sse_generator(request, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
