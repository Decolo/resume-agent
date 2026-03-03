"""Tests for Wire send/receive protocol."""

import pytest

from resume_agent.core.wire import QueueShutDown, Wire
from resume_agent.core.wire.types import (
    StepBegin,
    TextDelta,
    TurnBegin,
    TurnEnd,
)


@pytest.mark.asyncio
async def test_wire_message_ordering():
    """Messages arrive in send order via ui_side."""
    wire = Wire()
    ui = wire.ui_side()

    wire.soul_side.send(TurnBegin(user_input="hello"))
    wire.soul_side.send(TextDelta(text="world"))
    wire.soul_side.send(TurnEnd(final_text="world"))
    wire.shutdown()

    msg1 = await ui.receive()
    msg2 = await ui.receive()
    msg3 = await ui.receive()

    assert isinstance(msg1, TurnBegin)
    assert msg1.user_input == "hello"
    assert isinstance(msg2, TextDelta)
    assert msg2.text == "world"
    assert isinstance(msg3, TurnEnd)
    assert msg3.final_text == "world"

    with pytest.raises(QueueShutDown):
        await ui.receive()


@pytest.mark.asyncio
async def test_wire_multiple_consumers():
    """Two UI sides both receive every message."""
    wire = Wire()
    ui1 = wire.ui_side()
    ui2 = wire.ui_side()

    wire.soul_side.send(StepBegin(n=1))
    wire.shutdown()

    msg1 = await ui1.receive()
    msg2 = await ui2.receive()

    assert isinstance(msg1, StepBegin) and msg1.n == 1
    assert isinstance(msg2, StepBegin) and msg2.n == 1


@pytest.mark.asyncio
async def test_wire_send_after_shutdown_is_silent():
    """Sending after shutdown does not raise (graceful degradation)."""
    wire = Wire()
    wire.shutdown()
    # Should not raise
    wire.soul_side.send(TextDelta(text="too late"))
