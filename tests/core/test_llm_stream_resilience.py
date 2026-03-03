"""Tests for LLMAgent stream transport fallback behavior."""

import pytest

from resume_agent.core.llm import LLMAgent, LLMConfig
from resume_agent.providers.types import LLMResponse


class _StreamErrorProvider:
    def __init__(self, stream_error: Exception, fallback_response: LLMResponse | None = None):
        self._stream_error = stream_error
        self._fallback_response = fallback_response or LLMResponse(text="fallback-ok", function_calls=[])
        self.generate_calls = 0

    async def generate(self, messages, tools, config):  # noqa: ANN001
        self.generate_calls += 1
        return self._fallback_response

    async def generate_stream(self, messages, tools, config):  # noqa: ANN001
        raise self._stream_error
        yield  # pragma: no cover


def _make_agent() -> LLMAgent:
    config = LLMConfig(api_key="test", provider="gemini", model="test-model")
    return LLMAgent(config=config, system_prompt="test")


@pytest.mark.asyncio
async def test_stream_transient_error_falls_back_to_non_stream():
    """Transient stream transport errors should fallback to non-stream call."""
    agent = _make_agent()
    provider = _StreamErrorProvider(
        stream_error=ConnectionError("server disconnected"),
        fallback_response=LLMResponse(text="fallback-ok", function_calls=[]),
    )
    agent.provider = provider

    response = await agent._call_llm_with_resilience(stream=True)

    assert response.text == "fallback-ok"
    assert provider.generate_calls == 1


@pytest.mark.asyncio
async def test_stream_non_transient_error_is_raised():
    """Permanent stream errors should be raised without fallback."""
    agent = _make_agent()
    provider = _StreamErrorProvider(stream_error=ValueError("bad request payload"))
    agent.provider = provider

    with pytest.raises(ValueError, match="bad request payload"):
        await agent._call_llm_with_resilience(stream=True)

    assert provider.generate_calls == 0
