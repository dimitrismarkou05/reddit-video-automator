"""Server-Sent Events for real-time notifications and progress updates."""

import asyncio
import json
from typing import AsyncGenerator
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()

_STOP = object()

_live_queues: set[asyncio.Queue] = set()

def signal_shutdown() -> None:
    for q in list(_live_queues):
        try:
            q.put_nowait(_STOP)
        except Exception:
            pass

class SSEQueue:
    def __init__(self):
        self._queues: list[asyncio.Queue] = []

    async def connect(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues.append(queue)
        _live_queues.add(queue)
        return queue

    def disconnect(self, queue: asyncio.Queue) -> None:
        try:
            self._queues.remove(queue)
        except ValueError:
            pass
        _live_queues.discard(queue)

    async def broadcast(self, event_type: str, data: dict) -> None:
        message = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        dead: list[asyncio.Queue] = []
        for queue in list(self._queues):
            try:
                queue.put_nowait(message)
            except Exception:
                dead.append(queue)
        for q in dead:
            self.disconnect(q)

notification_queue = SSEQueue()

async def sse_generator(
    request: Request, queue: asyncio.Queue
) -> AsyncGenerator[str, None]:
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                yield ":keep-alive\n\n"
                continue

            if message is _STOP:
                break

            yield message

    except asyncio.CancelledError:
        raise
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
    try:
        from video.pipeline import VideoPipeline
        from database import SessionLocal

        db = SessionLocal()
        try:
            pipeline = VideoPipeline(db)
            progress = pipeline.get_progress(video_id)
            await queue.put(f"event: progress\ndata: {json.dumps(progress)}\n\n")
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