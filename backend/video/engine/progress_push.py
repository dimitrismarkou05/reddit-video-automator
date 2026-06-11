"""Push-based progress channel.

The pipeline calls push_progress() after every DB commit.  SSE connections
subscribe via subscribe() and receive events with sub-second latency instead of
the previous 1.5-second DB poll interval.

The implementation is asyncio-safe and also safe to call from worker threads
(uses loop.call_soon_threadsafe when necessary).
"""

import asyncio
import logging
import threading
from typing import Dict, Set

logger = logging.getLogger(__name__)

# video_id -> set of asyncio.Queue instances (one per open SSE connection)
_channels: Dict[int, Set[asyncio.Queue]] = {}
_lock = threading.Lock()


def subscribe(video_id: int) -> asyncio.Queue:
    """Create a queue for a new SSE connection and return it."""
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    with _lock:
        _channels.setdefault(video_id, set()).add(q)
    logger.debug(f"[ProgressPush] Subscribed queue for video {video_id}")
    return q


def unsubscribe(video_id: int, q: asyncio.Queue) -> None:
    """Remove a queue when the SSE connection closes."""
    with _lock:
        ch = _channels.get(video_id)
        if ch:
            ch.discard(q)
            if not ch:
                del _channels[video_id]
    logger.debug(f"[ProgressPush] Unsubscribed queue for video {video_id}")


def push_progress(video_id: int, data: dict) -> None:
    """Deliver *data* to every SSE connection watching *video_id*.

    Safe to call from:
    - Coroutines running in the event loop (uses put_nowait directly).
    - Worker threads (uses loop.call_soon_threadsafe).
    """
    with _lock:
        queues = list(_channels.get(video_id, []))
    if not queues:
        return

    def _put(q: asyncio.Queue) -> None:
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            # Drop the oldest item and enqueue the new one.
            try:
                q.get_nowait()
                q.put_nowait(data)
            except Exception:
                pass
        except Exception:
            pass

    # Try to get the running event loop; fall back to thread-safe scheduling.
    try:
        loop = asyncio.get_running_loop()
        for q in queues:
            loop.call_soon(_put, q)
    except RuntimeError:
        # Called from a worker thread – schedule into the event loop.
        try:
            loop = asyncio.get_event_loop()
            for q in queues:
                loop.call_soon_threadsafe(_put, q)
        except Exception as exc:
            logger.debug(f"[ProgressPush] Could not schedule push for {video_id}: {exc}")
