"""Tests for Queue + BroadcastQueue infrastructure."""

import asyncio

import pytest

from resume_agent.core.wire.queue import BroadcastQueue, Queue, QueueShutDown


@pytest.mark.asyncio
async def test_queue_send_receive_ordering():
    """Messages come out in FIFO order."""
    q: Queue[int] = Queue()
    q.put_nowait(1)
    q.put_nowait(2)
    q.put_nowait(3)
    assert await q.get() == 1
    assert await q.get() == 2
    assert await q.get() == 3


@pytest.mark.asyncio
async def test_queue_shutdown_raises():
    """get() raises QueueShutDown after shutdown."""
    q: Queue[int] = Queue()
    q.put_nowait(42)
    q.shutdown()
    # Existing item can still be read
    assert await q.get() == 42
    # Next get raises
    with pytest.raises(QueueShutDown):
        await q.get()


@pytest.mark.asyncio
async def test_queue_put_after_shutdown_raises():
    """put_nowait raises QueueShutDown after shutdown."""
    q: Queue[int] = Queue()
    q.shutdown()
    with pytest.raises(QueueShutDown):
        q.put_nowait(1)


@pytest.mark.asyncio
async def test_queue_get_blocks_until_item():
    """get() blocks until an item is available."""
    q: Queue[str] = Queue()

    async def delayed_put():
        await asyncio.sleep(0.01)
        q.put_nowait("hello")

    asyncio.create_task(delayed_put())
    result = await q.get()
    assert result == "hello"


@pytest.mark.asyncio
async def test_broadcast_spmc_fanout():
    """All subscribers receive every published message."""
    bq: BroadcastQueue[str] = BroadcastQueue()
    sub1 = bq.subscribe()
    sub2 = bq.subscribe()

    bq.publish_nowait("a")
    bq.publish_nowait("b")

    assert await sub1.get() == "a"
    assert await sub1.get() == "b"
    assert await sub2.get() == "a"
    assert await sub2.get() == "b"


@pytest.mark.asyncio
async def test_broadcast_shutdown_propagates():
    """shutdown() on BroadcastQueue shuts down all subscriber queues."""
    bq: BroadcastQueue[int] = BroadcastQueue()
    sub1 = bq.subscribe()
    sub2 = bq.subscribe()

    bq.publish_nowait(1)
    bq.shutdown()

    # Existing items can still be read
    assert await sub1.get() == 1
    assert await sub2.get() == 1

    # Then QueueShutDown is raised
    with pytest.raises(QueueShutDown):
        await sub1.get()
    with pytest.raises(QueueShutDown):
        await sub2.get()


@pytest.mark.asyncio
async def test_broadcast_late_subscriber_misses_earlier_messages():
    """A subscriber added after publish does not see earlier messages."""
    bq: BroadcastQueue[str] = BroadcastQueue()
    sub1 = bq.subscribe()
    bq.publish_nowait("early")

    sub2 = bq.subscribe()
    bq.publish_nowait("late")

    assert await sub1.get() == "early"
    assert await sub1.get() == "late"
    # sub2 only gets "late"
    assert await sub2.get() == "late"
