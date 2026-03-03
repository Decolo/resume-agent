"""Async queue primitives with shutdown support and broadcast fan-out."""

from __future__ import annotations

import asyncio
import sys
from typing import Generic, TypeVar

T = TypeVar("T")

if sys.version_info >= (3, 13):
    QueueShutDown = asyncio.QueueShutDown

    class Queue(asyncio.Queue, Generic[T]):
        """Asyncio Queue with shutdown support (native in 3.13+)."""

else:

    class QueueShutDown(Exception):
        """Raised when operating on a shut-down queue."""

    class _Shutdown:
        """Sentinel for queue shutdown."""

    _SHUTDOWN = _Shutdown()

    class Queue(asyncio.Queue, Generic[T]):
        """Asyncio Queue with shutdown support for Python < 3.13."""

        def __init__(self) -> None:
            super().__init__()
            self._shutdown = False

        def shutdown(self, immediate: bool = False) -> None:
            if self._shutdown:
                return
            self._shutdown = True
            if immediate:
                self._queue.clear()

            # Enqueue enough sentinels to wake all blocked getters
            getters = list(getattr(self, "_getters", []))
            count = max(1, len(getters))
            for _ in range(count):
                try:
                    super().put_nowait(_SHUTDOWN)
                except asyncio.QueueFull:
                    self._queue.clear()
                    super().put_nowait(_SHUTDOWN)

        async def get(self) -> T:
            if self._shutdown and self.empty():
                raise QueueShutDown
            item = await super().get()
            if isinstance(item, _Shutdown):
                raise QueueShutDown
            return item

        def get_nowait(self) -> T:
            if self._shutdown and self.empty():
                raise QueueShutDown
            item = super().get_nowait()
            if isinstance(item, _Shutdown):
                raise QueueShutDown
            return item

        async def put(self, item: T) -> None:
            if self._shutdown:
                raise QueueShutDown
            await super().put(item)

        def put_nowait(self, item: T) -> None:
            if self._shutdown:
                raise QueueShutDown
            super().put_nowait(item)


class BroadcastQueue(Generic[T]):
    """Fan-out queue: every subscriber receives every published item."""

    def __init__(self) -> None:
        self._queues: set[Queue[T]] = set()

    def subscribe(self) -> Queue[T]:
        queue: Queue[T] = Queue()
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: Queue[T]) -> None:
        self._queues.discard(queue)

    def publish_nowait(self, item: T) -> None:
        for queue in self._queues:
            queue.put_nowait(item)

    def shutdown(self, immediate: bool = False) -> None:
        for queue in self._queues:
            queue.shutdown(immediate=immediate)
        self._queues.clear()
