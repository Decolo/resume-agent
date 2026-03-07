"""Tests for LLMAgent wire-mode integration."""

import asyncio

import pytest

from resume_agent.core.llm import LLMAgent, LLMConfig
from resume_agent.core.wire import QueueShutDown, Wire
from resume_agent.core.wire.types import (
    ApprovalRequest,
    ToolCallEvent,
    ToolResultEvent,
    TurnBegin,
    TurnEnd,
)
from resume_agent.providers.types import FunctionCall, LLMResponse


class _ScriptedProvider:
    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self.generate_calls = 0

    async def generate(self, messages, tools, config):  # noqa: ANN001
        self.generate_calls += 1
        if self._responses:
            return self._responses.pop(0)
        return LLMResponse(text="done", function_calls=[])

    async def generate_stream(self, messages, tools, config):  # noqa: ANN001
        raise AssertionError("streaming path is not expected in this test")
        yield  # pragma: no cover


class _RecordingSessionManager:
    def __init__(self):
        self.calls = []

    def save_session(self, agent, session_id=None, session_name=None):  # noqa: ANN001
        self.calls.append(
            {
                "agent": agent,
                "session_id": session_id,
                "session_name": session_name,
            }
        )
        return f"session_{len(self.calls)}"


def _make_agent() -> LLMAgent:
    config = LLMConfig(api_key="test", provider="gemini", model="test-model")
    return LLMAgent(config=config, system_prompt="test")


def _register_echo_tool(agent: LLMAgent) -> None:
    def echo_tool(text: str = "") -> str:
        return f"echoed: {text}"

    agent.register_tool(
        name="echo",
        description="Echo text",
        parameters={"properties": {"text": {"type": "string"}}, "required": ["text"]},
        func=echo_tool,
    )


def _register_write_tool(agent: LLMAgent) -> None:
    def file_write(file_path: str = "", content: str = "") -> str:
        return f"wrote {len(content)} chars to {file_path}"

    agent.register_tool(
        name="file_write",
        description="Write file",
        parameters={
            "properties": {
                "file_path": {"type": "string", "required": True},
                "content": {"type": "string", "required": True},
            },
            "required": ["file_path", "content"],
        },
        func=file_write,
    )


def _register_read_tool(agent: LLMAgent) -> None:
    def file_read(path: str = "") -> str:
        return f"read {path}"

    agent.register_tool(
        name="file_read",
        description="Read file",
        parameters={"properties": {"path": {"type": "string"}}, "required": ["path"]},
        func=file_read,
    )


def _register_write_tool_path(agent: LLMAgent) -> None:
    def file_write(path: str = "", content: str = "") -> str:
        return f"Successfully wrote {len(content)} characters to {path}"

    agent.register_tool(
        name="file_write",
        description="Write file",
        parameters={
            "properties": {
                "path": {"type": "string", "required": True},
                "content": {"type": "string", "required": True},
            },
            "required": ["path", "content"],
        },
        func=file_write,
    )


async def _collect_from_ui(ui, timeout: float = 5.0) -> list:
    """Collect all wire messages from a pre-subscribed UI side until shutdown."""
    messages = []
    try:
        while True:
            msg = await asyncio.wait_for(ui.receive(), timeout=timeout)
            messages.append(msg)
    except (QueueShutDown, asyncio.TimeoutError):
        pass
    return messages


@pytest.mark.asyncio
async def test_wire_emits_turn_lifecycle():
    """Wire mode emits TurnBegin -> StepBegin -> TurnEnd for a text-only response."""
    agent = _make_agent()
    agent.provider = _ScriptedProvider([LLMResponse(text="Hello world", function_calls=[])])

    wire = Wire()
    ui = wire.ui_side()

    collector = asyncio.create_task(_collect_from_ui(ui))
    response = await agent.run("hi", wire=wire)
    wire.shutdown()
    messages = await collector

    assert response == "Hello world"
    types = [type(m).__name__ for m in messages]
    assert "TurnBegin" in types
    assert "StepBegin" in types
    assert "TurnEnd" in types
    assert isinstance(messages[0], TurnBegin) and messages[0].user_input == "hi"
    assert isinstance(messages[-1], TurnEnd) and messages[-1].final_text == "Hello world"


@pytest.mark.asyncio
async def test_text_only_turn_auto_saves_with_wire_no_ui_subscriber():
    """Text-only turns should auto-save even when no UI subscriber is attached."""
    agent = _make_agent()
    session_manager = _RecordingSessionManager()
    parent_agent = object()
    agent.session_manager = session_manager
    agent._parent_agent = parent_agent
    agent.provider = _ScriptedProvider([LLMResponse(text="Hello world", function_calls=[])])

    wire = Wire()
    response = await agent.run("hi", wire=wire)
    wire.shutdown()

    assert response == "Hello world"
    assert len(session_manager.calls) == 1
    assert session_manager.calls[0]["agent"] is parent_agent
    assert session_manager.calls[0]["session_id"] is None
    assert agent.current_session_id == "session_1"


@pytest.mark.asyncio
async def test_text_only_turn_auto_saves_with_wire():
    """Wire mode should also auto-save text-only turns."""
    agent = _make_agent()
    session_manager = _RecordingSessionManager()
    parent_agent = object()
    agent.session_manager = session_manager
    agent._parent_agent = parent_agent
    agent.provider = _ScriptedProvider([LLMResponse(text="Hello world", function_calls=[])])

    wire = Wire()
    response = await agent.run("hi", wire=wire)
    wire.shutdown()

    assert response == "Hello world"
    assert len(session_manager.calls) == 1
    assert session_manager.calls[0]["agent"] is parent_agent
    assert session_manager.calls[0]["session_id"] is None
    assert agent.current_session_id == "session_1"


@pytest.mark.asyncio
async def test_wire_emits_tool_events():
    """Wire mode emits ToolCallEvent and ToolResultEvent for tool calls."""
    agent = _make_agent()
    _register_echo_tool(agent)

    tool_response = LLMResponse(
        text="",
        function_calls=[FunctionCall(name="echo", arguments={"text": "test"}, id="c1")],
    )
    final_response = LLMResponse(text="Done", function_calls=[])

    agent.provider = _ScriptedProvider([tool_response, final_response])

    wire = Wire()
    ui = wire.ui_side()
    collector = asyncio.create_task(_collect_from_ui(ui))
    response = await agent.run("echo test", wire=wire)
    wire.shutdown()
    messages = await collector

    assert response == "Done"
    tool_calls = [m for m in messages if isinstance(m, ToolCallEvent)]
    tool_results = [m for m in messages if isinstance(m, ToolResultEvent)]
    assert len(tool_calls) == 1 and tool_calls[0].name == "echo"
    assert len(tool_results) == 1 and "echoed: test" in tool_results[0].result


@pytest.mark.asyncio
async def test_wire_approval_approve():
    """Write tool triggers ApprovalRequest; approving lets tool execute."""
    agent = _make_agent()
    _register_write_tool(agent)

    tool_response = LLMResponse(
        text="",
        function_calls=[FunctionCall(name="file_write", arguments={"file_path": "a.txt", "content": "hi"}, id="c1")],
    )
    final_response = LLMResponse(text="File written", function_calls=[])

    agent.provider = _ScriptedProvider([tool_response, final_response])

    wire = Wire()
    # Two UI sides: one to auto-approve, one to collect messages
    approver_ui = wire.ui_side()
    collector_ui = wire.ui_side()

    async def auto_approve():
        try:
            while True:
                msg = await approver_ui.receive()
                if isinstance(msg, ApprovalRequest):
                    msg.resolve("approve")
        except QueueShutDown:
            pass

    approve_task = asyncio.create_task(auto_approve())
    collector = asyncio.create_task(_collect_from_ui(collector_ui))
    response = await agent.run("write a file", wire=wire)
    wire.shutdown()
    messages = await collector
    await approve_task

    assert response == "File written"
    approval_reqs = [m for m in messages if isinstance(m, ApprovalRequest)]
    assert len(approval_reqs) == 1
    tool_results = [m for m in messages if isinstance(m, ToolResultEvent)]
    assert len(tool_results) == 1 and tool_results[0].success is True


@pytest.mark.asyncio
async def test_wire_approval_reject():
    """Rejecting approval injects rejection into history and continues loop."""
    agent = _make_agent()
    _register_write_tool(agent)

    tool_response = LLMResponse(
        text="",
        function_calls=[FunctionCall(name="file_write", arguments={"file_path": "a.txt", "content": "hi"}, id="c1")],
    )
    final_response = LLMResponse(text="OK, cancelled", function_calls=[])

    agent.provider = _ScriptedProvider([tool_response, final_response])

    wire = Wire()
    rejector_ui = wire.ui_side()
    collector_ui = wire.ui_side()

    async def auto_reject():
        try:
            while True:
                msg = await rejector_ui.receive()
                if isinstance(msg, ApprovalRequest):
                    msg.resolve("reject")
        except QueueShutDown:
            pass

    reject_task = asyncio.create_task(auto_reject())
    collector = asyncio.create_task(_collect_from_ui(collector_ui))
    response = await agent.run("write a file", wire=wire)
    wire.shutdown()
    messages = await collector
    await reject_task

    assert response == "OK, cancelled"
    tool_results = [m for m in messages if isinstance(m, ToolResultEvent)]
    assert len(tool_results) == 0


@pytest.mark.asyncio
async def test_wire_approve_all_persists_across_turns():
    """approve_all should enable global auto-approve for subsequent turns."""
    agent = _make_agent()
    _register_write_tool(agent)

    first_tool = LLMResponse(
        text="",
        function_calls=[FunctionCall(name="file_write", arguments={"file_path": "a.txt", "content": "one"}, id="c1")],
    )
    first_final = LLMResponse(text="first done", function_calls=[])
    agent.provider = _ScriptedProvider([first_tool, first_final])

    wire1 = Wire()
    approver_ui = wire1.ui_side()
    collector1 = wire1.ui_side()

    async def auto_approve_all():
        try:
            while True:
                msg = await approver_ui.receive()
                if isinstance(msg, ApprovalRequest):
                    msg.resolve("approve_all")
        except QueueShutDown:
            pass

    approve_task = asyncio.create_task(auto_approve_all())
    collect_task = asyncio.create_task(_collect_from_ui(collector1))
    response1 = await agent.run("write first", wire=wire1)
    wire1.shutdown()
    messages1 = await collect_task
    await approve_task

    assert response1 == "first done"
    assert any(isinstance(m, ApprovalRequest) for m in messages1)
    assert agent.is_auto_approve_enabled() is True

    second_tool = LLMResponse(
        text="",
        function_calls=[FunctionCall(name="file_write", arguments={"file_path": "b.txt", "content": "two"}, id="c2")],
    )
    second_final = LLMResponse(text="second done", function_calls=[])
    agent.provider = _ScriptedProvider([second_tool, second_final])

    wire2 = Wire()
    collector2 = wire2.ui_side()
    collect_task2 = asyncio.create_task(_collect_from_ui(collector2))
    response2 = await agent.run("write second", wire=wire2)
    wire2.shutdown()
    messages2 = await collect_task2

    assert response2 == "second done"
    assert not any(isinstance(m, ApprovalRequest) for m in messages2)


@pytest.mark.asyncio
async def test_wire_write_call_fails_fast_without_ui_subscriber():
    """When no UI subscriber exists and no handler is configured, write call should fail fast."""
    agent = _make_agent()
    _register_write_tool(agent)

    tool_response = LLMResponse(
        text="",
        function_calls=[FunctionCall(name="file_write", arguments={"file_path": "a.txt", "content": "hi"}, id="c1")],
    )

    agent.provider = _ScriptedProvider([tool_response])
    wire = Wire()
    response = await agent.run("write a file", wire=wire)
    wire.shutdown()

    assert "require approval" in response.lower()
    assert "no wire ui consumer" in response.lower()


@pytest.mark.asyncio
async def test_wire_write_call_uses_approval_handler_when_configured():
    """Approval handler can authorize writes even when no UI subscriber is attached."""
    agent = _make_agent()
    _register_write_tool(agent)

    async def approve_handler(function_calls):  # noqa: ANN001
        return function_calls, ""

    agent.set_approval_handler(approve_handler)
    agent.provider = _ScriptedProvider(
        [
            LLMResponse(
                text="",
                function_calls=[
                    FunctionCall(name="file_write", arguments={"file_path": "a.txt", "content": "hi"}, id="c1")
                ],
            ),
            LLMResponse(text="File written", function_calls=[]),
        ]
    )

    wire = Wire()
    response = await agent.run("write a file", wire=wire)
    wire.shutdown()
    assert response == "File written"


@pytest.mark.asyncio
async def test_wire_invalid_tool_call_missing_args_aborts_turn(monkeypatch):
    """Invalid tool-call args should abort the turn to avoid approval loops."""
    agent = _make_agent()
    _register_write_tool(agent)

    # Provider keeps returning the same invalid write call; agent should stop
    # after first failed execution and return control to CLI.
    tool_response = LLMResponse(
        text="",
        function_calls=[FunctionCall(name="file_write", arguments={}, id="c1")],
    )
    agent.provider = _ScriptedProvider([tool_response, tool_response, LLMResponse(text="unused", function_calls=[])])

    wire = Wire()
    approver_ui = wire.ui_side()
    collector_ui = wire.ui_side()

    async def auto_approve():
        try:
            while True:
                msg = await approver_ui.receive()
                if isinstance(msg, ApprovalRequest):
                    msg.resolve("approve")
        except QueueShutDown:
            pass

    approve_task = asyncio.create_task(auto_approve())
    collector = asyncio.create_task(_collect_from_ui(collector_ui))
    response = await agent.run("write with missing args", wire=wire)
    wire.shutdown()
    messages = await collector
    await approve_task

    assert "Invalid tool call for 'file_write'" in response
    assert "Turn aborted to prevent repeated approval/tool loops" in response
    approval_reqs = [m for m in messages if isinstance(m, ApprovalRequest)]
    assert len(approval_reqs) == 1


@pytest.mark.asyncio
async def test_wire_replay_verbose_repeated_writes_stops_before_invalid_bash():
    """Replay 2026-03-07 verbose pattern and ensure guard exits before invalid bash call."""
    agent = _make_agent()
    _register_read_tool(agent)
    _register_write_tool_path(agent)

    truncated_html = (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '    <meta charset="UTF-8">\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0\\'
    )

    replay_responses = [
        LLMResponse(
            text="Read both HTML files first.",
            function_calls=[
                FunctionCall(
                    name="file_read",
                    arguments={"path": "frontend-resume-optimized-2026-03-06.html"},
                    id="file_read:0",
                ),
                FunctionCall(
                    name="file_read",
                    arguments={"path": "frontend-resume-improved-2026-02-03.html"},
                    id="file_read:1",
                ),
            ],
        ),
        LLMResponse(
            text="I'll align the file now.",
            function_calls=[
                FunctionCall(
                    name="file_write",
                    arguments={
                        "path": "frontend-resume-optimized-2026-03-06.html",
                        "content": truncated_html,
                    },
                    id="file_write:2",
                )
            ],
        ),
        LLMResponse(
            text="I need to write the complete file with proper content.",
            function_calls=[
                FunctionCall(
                    name="file_write",
                    arguments={
                        "path": "frontend-resume-optimized-2026-03-06.html",
                        "content": truncated_html,
                    },
                    id="file_write:3",
                )
            ],
        ),
        LLMResponse(
            text="The file seems to be getting truncated. Let me write it in one go.",
            function_calls=[
                FunctionCall(
                    name="file_write",
                    arguments={
                        "path": "frontend-resume-optimized-2026-03-06.html",
                        "content": truncated_html,
                    },
                    id="file_write:4",
                )
            ],
        ),
        LLMResponse(
            text="I notice truncation. I will use bash.",
            function_calls=[FunctionCall(name="bash", arguments={}, id="bash:6")],
        ),
    ]
    provider = _ScriptedProvider(replay_responses)
    agent.provider = provider

    wire = Wire()
    approver_ui = wire.ui_side()
    collector_ui = wire.ui_side()

    async def auto_approve():
        try:
            while True:
                msg = await approver_ui.receive()
                if isinstance(msg, ApprovalRequest):
                    msg.resolve("approve")
        except QueueShutDown:
            pass

    approve_task = asyncio.create_task(auto_approve())
    collector = asyncio.create_task(_collect_from_ui(collector_ui))
    response = await agent.run("align html display", wire=wire)
    wire.shutdown()
    messages = await collector
    await approve_task

    assert "repeated identical write operations detected" in response
    assert "Invalid tool call for 'bash'" not in response

    approvals = [m for m in messages if isinstance(m, ApprovalRequest)]
    assert len(approvals) == 3

    tool_calls = [m for m in messages if isinstance(m, ToolCallEvent)]
    names = [m.name for m in tool_calls]
    assert names.count("file_read") == 2
    assert names.count("file_write") == 3
    assert "bash" not in names

    # Should stop before consuming the scripted bash response.
    assert provider.generate_calls == 4
