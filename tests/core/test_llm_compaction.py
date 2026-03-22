"""Tests for LLMAgent history compaction behavior."""

from __future__ import annotations

import pytest

from resume_agent.core.llm import COMPRESSION_STATE_PREFIX, LLMAgent, LLMConfig
from resume_agent.providers.types import FunctionCall, FunctionResponse, LLMResponse, Message, MessagePart, StreamDelta


class _CompactionAwareProvider:
    def __init__(self, *, overflow_on_first_main_call: bool = False) -> None:
        self.calls: list[dict] = []
        self._overflow_on_first_main_call = overflow_on_first_main_call
        self._main_calls = 0

    async def generate(self, messages, tools, config):  # noqa: ANN001
        call = {
            "messages": list(messages),
            "tools": tools,
            "system_prompt": config.system_prompt,
        }
        self.calls.append(call)

        if "Compress the provided conversation history" in (config.system_prompt or ""):
            return LLMResponse(
                text=(
                    '{"summary_text":"Earlier resume tailoring decisions","session_intent":"Tailor resume",'
                    '"file_modifications":["resume.md"],"decisions":["Condense early context"],'
                    '"open_questions":[],"next_steps":["Continue editing latest bullet"]}'
                ),
                function_calls=[],
            )

        self._main_calls += 1
        if self._overflow_on_first_main_call and self._main_calls == 1:
            raise RuntimeError("context window exceeded")

        return LLMResponse(text="final answer", function_calls=[])

    async def generate_stream(self, messages, tools, config):  # noqa: ANN001
        if False:
            yield StreamDelta(text="")


def _make_agent() -> LLMAgent:
    agent = LLMAgent(
        LLMConfig(
            api_key="test-key",
            provider="gemini",
            model="test-model",
            max_tokens=16,
        ),
        system_prompt="test",
    )
    return agent


def _seed_long_history(agent: LLMAgent) -> None:
    agent.history_manager.max_tokens = 70
    agent.history_manager.tail_tokens = 25
    agent.history_manager.add_message(Message.user("Need help tailoring this resume for a backend platform role."))
    agent.history_manager.add_message(Message.assistant("I inspected the current resume and found broad bullets."))
    agent.history_manager.add_message(Message.user("Rewrite the experience bullet to emphasize Python ownership."))
    agent.history_manager.add_message(Message.assistant("I can rewrite that bullet and keep the rest unchanged."))


@pytest.mark.asyncio
async def test_call_llm_compacts_history_before_main_provider_request():
    agent = _make_agent()
    provider = _CompactionAwareProvider()
    agent.provider = provider
    _seed_long_history(agent)

    response = await agent._call_llm()

    assert response.text == "final answer"
    assert len(provider.calls) == 2
    assert provider.calls[0]["tools"] is None
    assert provider.calls[1]["messages"][0].parts[0].text.startswith(COMPRESSION_STATE_PREFIX)
    assert agent.history_manager.get_compression_state() is not None
    assert len(agent.history_manager.get_compaction_checkpoints()) == 1


@pytest.mark.asyncio
async def test_call_llm_compacts_once_and_retries_after_context_overflow():
    agent = _make_agent()
    provider = _CompactionAwareProvider(overflow_on_first_main_call=True)
    agent.provider = provider
    _seed_long_history(agent)
    agent.history_manager.max_tokens = 10_000

    response = await agent._call_llm()

    assert response.text == "final answer"
    assert len(provider.calls) == 3
    assert (
        provider.calls[0]["messages"][0].parts[0].text == "Need help tailoring this resume for a backend platform role."
    )
    assert provider.calls[1]["tools"] is None
    assert provider.calls[2]["messages"][0].parts[0].text.startswith(COMPRESSION_STATE_PREFIX)
    assert len(agent.history_manager.get_compaction_checkpoints()) == 1


@pytest.mark.asyncio
async def test_compaction_summarizer_sends_plain_text_transcript_not_tool_protocol():
    agent = _make_agent()
    provider = _CompactionAwareProvider()
    agent.provider = provider

    messages = [
        Message.user("Read the resume and update the latest bullet."),
        Message(
            role="assistant",
            parts=[MessagePart.from_function_call(FunctionCall(name="file_read", arguments={"path": "resume.md"}))],
        ),
        Message(
            role="tool",
            parts=[
                MessagePart.from_function_response(
                    FunctionResponse(name="file_read", response={"result": "Loaded resume.md"})
                )
            ],
        ),
        Message.assistant("I found the bullet that needs revision."),
    ]

    summary = await agent._summarize_history_for_compaction(messages, prior_state=None)

    assert summary.summary_text == "Earlier resume tailoring decisions"
    assert len(provider.calls) == 1
    compaction_call = provider.calls[0]
    assert compaction_call["tools"] is None
    assert len(compaction_call["messages"]) == 1
    assert compaction_call["messages"][0].role == "user"
    transcript = compaction_call["messages"][0].parts[0].text
    assert "USER: Read the resume and update the latest bullet." in transcript
    assert 'ASSISTANT_TOOL_CALL: file_read args={"path": "resume.md"}' in transcript
    assert 'TOOL_RESULT: file_read result={"result": "Loaded resume.md"}' in transcript
