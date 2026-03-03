"""Tests for tool-call policy enforcement in LLMAgent."""

from __future__ import annotations

import pytest

from resume_agent.core.llm import LLMAgent, LLMConfig
from resume_agent.providers.types import FunctionCall, LLMResponse


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
async def test_run_blocks_job_detail_when_mixed_with_job_search_in_same_step():
    agent = _new_agent()
    search_calls: list[dict] = []
    detail_calls: list[dict] = []

    async def fake_search(**kwargs):
        search_calls.append(kwargs)
        return "search ok"

    async def fake_detail(**kwargs):
        detail_calls.append(kwargs)
        return "detail ok"

    agent.register_tool(
        name="job_search",
        description="search",
        parameters={"properties": {}, "required": []},
        func=fake_search,
    )
    agent.register_tool(
        name="job_detail",
        description="detail",
        parameters={"properties": {}, "required": []},
        func=fake_detail,
    )
    agent.provider = _FakeProvider(
        responses=[
            LLMResponse(
                function_calls=[
                    FunctionCall(name="job_search", arguments={"keywords": "front end"}, id="call_s"),
                    FunctionCall(
                        name="job_detail",
                        arguments={"job_url": "https://www.linkedin.com/jobs/view/4353119521/"},
                        id="call_d",
                    ),
                ]
            ),
            LLMResponse(text="final"),
        ]
    )

    result = await agent.run("search jobs", max_steps=4)

    assert result == "final"
    assert len(search_calls) == 1
    assert len(detail_calls) == 0

    tool_messages = [m for m in agent.history_manager.get_history() if m.role == "tool"]
    assert tool_messages
    responses = [part.function_response for part in tool_messages[0].parts if part.function_response]
    assert any(r and r.name == "job_search" for r in responses)
    assert any(r and r.name == "job_detail" and "Rejected by policy" in r.response.get("result", "") for r in responses)


@pytest.mark.asyncio
async def test_approve_pending_tool_calls_applies_same_job_policy():
    agent = _new_agent()
    search_calls: list[dict] = []
    detail_calls: list[dict] = []

    async def fake_search(**kwargs):
        search_calls.append(kwargs)
        return "search ok"

    async def fake_detail(**kwargs):
        detail_calls.append(kwargs)
        return "detail ok"

    agent.register_tool(
        name="job_search",
        description="search",
        parameters={"properties": {}, "required": []},
        func=fake_search,
    )
    agent.register_tool(
        name="job_detail",
        description="detail",
        parameters={"properties": {}, "required": []},
        func=fake_detail,
    )

    agent._pending_tool_calls = [
        FunctionCall(name="job_search", arguments={"keywords": "frontend"}, id="call_s"),
        FunctionCall(
            name="job_detail",
            arguments={"job_url": "https://www.linkedin.com/jobs/view/4353119521/"},
            id="call_d",
        ),
    ]

    results = await agent.approve_pending_tool_calls()

    assert len(search_calls) == 1
    assert len(detail_calls) == 0
    assert any(item["name"] == "job_search" for item in results)
    assert any(item["name"] == "job_detail" and "Rejected by policy" in item["result"] for item in results)


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
