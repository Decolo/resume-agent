"""Wire protocol: event bus connecting agent loop (Soul) and UI.

Simplified from kimi-cli — no message merging, no file backend.
"""

from __future__ import annotations

from .queue import BroadcastQueue, Queue, QueueShutDown
from .types import WireMessage

__all__ = [
    "Wire",
    "WireSoulSide",
    "WireUISide",
    "QueueShutDown",
]


class Wire:
    """Single-producer / multi-consumer event bus for one agent turn."""

    def __init__(self) -> None:
        self._queue: BroadcastQueue[WireMessage] = BroadcastQueue()
        self._soul_side = WireSoulSide(self._queue)

    @property
    def soul_side(self) -> WireSoulSide:
        return self._soul_side

    def ui_side(self) -> WireUISide:
        """Create a new UI-side consumer (each gets its own subscription)."""
        return WireUISide(self._queue.subscribe())

    def shutdown(self) -> None:
        self._queue.shutdown()


class WireSoulSide:
    """Soul (agent loop) side — publishes events."""

    def __init__(self, queue: BroadcastQueue[WireMessage]) -> None:
        self._queue = queue

    def send(self, msg: WireMessage) -> None:
        try:
            self._queue.publish_nowait(msg)
        except QueueShutDown:
            pass


class WireUISide:
    """UI side — consumes events."""

    def __init__(self, queue: Queue[WireMessage]) -> None:
        self._queue = queue

    async def receive(self) -> WireMessage:
        """Await the next message. Raises QueueShutDown when wire is shut down."""
        return await self._queue.get()
