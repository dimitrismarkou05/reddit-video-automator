"""Server-Sent Events for real-time notifications."""

import asyncio
import json
import logging
from typing import AsyncGenerator
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()
logger = logging.getLogger(__name__)

_STOP = object()

_live_queues: set[asyncio.Queue] = set()


def signal_shutdown() -> None:
    logger.info("[NotificationSSE] Signaling shutdown")
    for q in list(_live_queues):
        try:
            q.put_nowait(_STOP)
        except Exception:
            pass


class SSEQueue:
    def __init__(self):
        self._queues: list[asyncio.Queue] = []
        self._closed = False

    async def connect(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)  # Bounded queue
        self._queues.append(queue)
        _live_queues.add(queue)
        logger.debug(f"[NotificationSSE] New connection, total queues: {len(self._queues)}")
        return queue

    def disconnect(self, queue: asyncio.Queue) -> None:
        try:
            self._queues.remove(queue)
        except ValueError:
            pass
        _live_queues.discard(queue)

    async def broadcast(self, event_type: str, data: dict) -> None:
        if self._closed:
            return
        message = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        dead: list[asyncio.Queue] = []
        for queue in list(self._queues):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                dead.append(queue)
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
                logger.debug("[NotificationSSE] Client disconnected")
                break
            try:
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                yield ":keep-alive\n\n"
                continue
            except asyncio.CancelledError:
                raise

            if message is _STOP:
                yield "event: shutdown\ndata: {}\n\n"
                break

            yield message

    except asyncio.CancelledError:
        logger.debug("[NotificationSSE] Generator cancelled")
        raise
    except Exception as e:
        logger.debug(f"[NotificationSSE] Generator error: {e}")
    finally:
        notification_queue.disconnect(queue)


@router.get("/notifications")
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
