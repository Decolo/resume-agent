"""Tests for the Approval subsystem."""

import asyncio

import pytest

from resume_agent.core.wire.approval import Approval, ApprovalState
from resume_agent.providers.types import FunctionCall


@pytest.mark.asyncio
async def test_yolo_returns_true_immediately():
    """When yolo=True, request() returns True without blocking."""
    approval = Approval(yolo=True)
    tool_calls = [FunctionCall(name="file_write", arguments={"path": "x"}, id="c1")]
    result = await approval.request("write_tool", tool_calls, "write file x")
    assert result is True


@pytest.mark.asyncio
async def test_non_yolo_blocks_until_resolved():
    """request() blocks until resolve_request is called."""
    approval = Approval(yolo=False)
    tool_calls = [FunctionCall(name="file_write", arguments={"path": "x"}, id="c1")]

    # Start the request in a background task
    req_task = asyncio.create_task(approval.request("write_tool", tool_calls, "write file x"))
    # Give the request time to enqueue
    await asyncio.sleep(0.01)

    # Fetch the pending request (soul-side)
    request = await approval.fetch_request()
    assert request.action == "write_tool"
    assert len(request.tool_calls) == 1

    # Resolve it
    approval.resolve_request(request.id, "approve")

    result = await req_task
    assert result is True


@pytest.mark.asyncio
async def test_reject_returns_false():
    """Rejecting a request makes request() return False."""
    approval = Approval(yolo=False)
    tool_calls = [FunctionCall(name="file_write", arguments={}, id="c1")]

    req_task = asyncio.create_task(approval.request("write_tool", tool_calls, "write"))
    await asyncio.sleep(0.01)

    request = await approval.fetch_request()
    approval.resolve_request(request.id, "reject")

    result = await req_task
    assert result is False


@pytest.mark.asyncio
async def test_approve_all_adds_to_auto_set():
    """approve_all adds the action to auto-approve, future requests auto-approve."""
    approval = Approval(yolo=False)
    tool_calls = [FunctionCall(name="file_write", arguments={}, id="c1")]

    # First request — manual approve_all
    req_task = asyncio.create_task(approval.request("write_tool", tool_calls, "first"))
    await asyncio.sleep(0.01)
    request = await approval.fetch_request()
    approval.resolve_request(request.id, "approve_all")
    result = await req_task
    assert result is True

    # Second request — should auto-approve without blocking
    result2 = await approval.request("write_tool", tool_calls, "second")
    assert result2 is True


@pytest.mark.asyncio
async def test_shared_state_via_constructor():
    """Two Approval instances sharing ApprovalState sync yolo mode."""
    state = ApprovalState(yolo=False)
    a1 = Approval(state=state)
    a2 = Approval(state=state)

    a1.set_yolo(True)
    assert a2.is_yolo() is True


@pytest.mark.asyncio
async def test_resolve_unknown_request_raises():
    """resolve_request with unknown ID raises KeyError."""
    approval = Approval()
    with pytest.raises(KeyError):
        approval.resolve_request("nonexistent", "approve")
