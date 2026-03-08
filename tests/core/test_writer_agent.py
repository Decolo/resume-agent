"""Regression tests for WriterAgent delegated execution behavior."""

import pytest

from resume_agent.core.agents.protocol import AgentTask
from resume_agent.core.agents.writer_agent import WriterAgent
from resume_agent.core.llm import LLMAgent, LLMConfig
from resume_agent.providers.types import FunctionCall, LLMResponse


class _ScriptedProvider:
    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)

    async def generate(self, messages, tools, config):  # noqa: ANN001
        if self._responses:
            return self._responses.pop(0)
        return LLMResponse(text="done", function_calls=[])

    async def generate_stream(self, messages, tools, config):  # noqa: ANN001
        raise AssertionError("streaming path is not expected in this test")
        yield  # pragma: no cover


@pytest.mark.asyncio
async def test_writer_agent_auto_approves_delegated_write_without_ui_subscriber():
    """Delegated writer run should not fail-fast on approval-gated file_write."""
    llm_agent = LLMAgent(
        config=LLMConfig(api_key="test", provider="gemini", model="test-model"),
        system_prompt="test",
    )

    def file_write(file_path: str = "", content: str = "") -> str:
        return f"wrote {len(content)} chars to {file_path}"

    llm_agent.register_tool(
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
        requires_approval=True,
    )

    llm_agent.provider = _ScriptedProvider(
        [
            LLMResponse(
                text="",
                function_calls=[
                    FunctionCall(name="file_write", arguments={"file_path": "a.txt", "content": "hi"}, id="c1")
                ],
            ),
            LLMResponse(text="writer done", function_calls=[]),
        ]
    )

    writer = WriterAgent(llm_agent=llm_agent)
    task = AgentTask(task_id="task_1", task_type="content_improve", description="Improve this resume bullet")

    result = await writer.execute(task)

    assert result.success is True
    assert result.output == "writer done"
    assert llm_agent._approval_handler is None
