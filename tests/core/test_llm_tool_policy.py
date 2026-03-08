"""Tests for tool-call validation and loop guard behavior in LLMAgent."""

from __future__ import annotations

import pytest

from resume_agent.core.llm import LLMAgent, LLMConfig
from resume_agent.providers.types import FunctionCall, FunctionResponse, LLMResponse, Message, MessagePart


class _FakeProvider:
    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)

    async def generate(self, messages, tools, config):  # noqa: ANN001
        if self._responses:
            return self._responses.pop(0)
        return LLMResponse(text="done")

    async def generate_stream(self, messages, tools, config):  # noqa: ANN001
        raise AssertionError("streaming path is not expected in this test")


def _new_agent() -> LLMAgent:
    return LLMAgent(
        LLMConfig(
            api_key="test-key",
            provider="kimi",
            model="kimi-k2",
            api_base="https://api.moonshot.cn/v1",
        ),
        system_prompt="test",
    )


@pytest.mark.asyncio
async def test_execute_tool_returns_validation_error_when_required_args_missing():
    agent = _new_agent()

    async def fake_write(**kwargs):
        return f"wrote {kwargs}"

    agent.register_tool(
        name="file_write",
        description="write",
        parameters={
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
        func=fake_write,
    )

    response = await agent._execute_tool(FunctionCall(name="file_write", arguments={}, id="call_w"))
    result = response.response.get("result", "")

    assert "Invalid tool call for 'file_write'" in result
    assert "path" in result
    assert "content" in result


@pytest.mark.asyncio
async def test_execute_tool_normalizes_file_path_alias_to_path():
    agent = _new_agent()
    received: list[dict] = []

    async def fake_read(**kwargs):
        received.append(kwargs)
        return f"read {kwargs.get('path')}"

    agent.register_tool(
        name="file_read",
        description="read",
        parameters={
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        func=fake_read,
    )

    response = await agent._execute_tool(
        FunctionCall(name="file_read", arguments={"file_path": "sample_resume.md"}, id="call_r")
    )

    assert received and received[0]["path"] == "sample_resume.md"
    assert "Error:" not in response.response.get("result", "")


@pytest.mark.asyncio
async def test_execute_tool_infers_path_from_recent_file_list_when_missing():
    agent = _new_agent()
    received: list[dict] = []

    async def fake_parse(**kwargs):
        received.append(kwargs)
        return f"parsed {kwargs.get('path')}"

    agent.register_tool(
        name="resume_parse",
        description="parse",
        parameters={
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        func=fake_parse,
    )

    # Seed history with a recent file_list result containing a single file.
    tool_msg = Message(
        role="tool",
        parts=[
            MessagePart.from_function_response(
                FunctionResponse(
                    name="file_list",
                    response={"result": "file\t1522\tsample_resume.md"},
                    call_id="call_list",
                )
            )
        ],
    )
    agent.history_manager.add_message(tool_msg, allow_incomplete=True)

    response = await agent._execute_tool(FunctionCall(name="resume_parse", arguments={}, id="call_p"))

    assert received and received[0]["path"] == "sample_resume.md"
    assert "parsed sample_resume.md" in response.response.get("result", "")


def test_repeated_write_guard_triggers_on_identical_rewrites():
    agent = _new_agent()
    state = {"last_write_sig": None, "same_write_repeats": 0}
    fc = FunctionCall(name="file_write", arguments={"path": "a.html", "content": "<html>ok</html>"}, id="c1")
    fr = FunctionResponse(
        name="file_write", response={"result": "Successfully wrote 15 characters to a.html"}, call_id="c1"
    )

    assert agent._check_repeated_write_guard([fc], [fr], state) is None
    assert agent._check_repeated_write_guard([fc], [fr], state) is None
    reason = agent._check_repeated_write_guard([fc], [fr], state)
    assert reason is not None
    assert "repeated identical mutating operations" in reason


def test_loop_guard_allows_long_tool_only_read_sequences_without_repeats():
    agent = _new_agent()
    state = {"last_call": None, "same_call_repeats": 0}

    for idx in range(12):
        fc = FunctionCall(name="file_read", arguments={"path": f"file_{idx}.md"}, id=f"c{idx}")
        reason = agent._check_loop_guard([fc], "", state)
        assert reason is None
