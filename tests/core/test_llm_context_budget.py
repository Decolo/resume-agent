"""Tests for runtime model capabilities and context budget estimation."""

from __future__ import annotations

import pytest

import resume_agent.core.llm as llm_module
from resume_agent.core.llm import LLMAgent, LLMConfig
from resume_agent.providers.types import LLMResponse, Message, ModelCapabilities, StreamDelta


class _CapabilityProvider:
    def __init__(self, capabilities: ModelCapabilities) -> None:
        self.capabilities = capabilities

    def get_model_capabilities(self) -> ModelCapabilities:
        return self.capabilities

    async def generate(self, messages, tools, config):  # noqa: ANN001
        return LLMResponse(text="ok", function_calls=[])

    async def generate_stream(self, messages, tools, config):  # noqa: ANN001
        if False:
            yield StreamDelta(text="")


def _make_agent(monkeypatch: pytest.MonkeyPatch, capabilities: ModelCapabilities, **config_kwargs) -> LLMAgent:
    monkeypatch.setattr(llm_module, "create_provider", lambda **kwargs: _CapabilityProvider(capabilities))
    return LLMAgent(
        LLMConfig(
            api_key="test-key",
            provider=config_kwargs.pop("provider", capabilities.provider or "gemini"),
            model=config_kwargs.pop("model", capabilities.model or "test-model"),
            max_tokens=config_kwargs.pop("max_tokens", 2048),
            context_window_override=config_kwargs.pop("context_window_override", None),
            **config_kwargs,
        ),
        system_prompt="Tailor the resume to a senior backend platform role.",
    )


def test_llm_agent_uses_runtime_context_window_for_history_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _make_agent(
        monkeypatch,
        ModelCapabilities(
            provider="gemini",
            model="gemini-test",
            context_window=32_000,
            max_output_tokens=4_096,
            source="api",
        ),
        max_tokens=3_000,
    )

    snapshot = agent.get_context_budget_snapshot()

    assert agent.history_manager.max_tokens == 32_000
    assert agent.history_manager.reserve_tokens == 3_000
    assert snapshot.context_window == 32_000
    assert snapshot.source == "api"


def test_llm_agent_context_window_override_wins_over_provider_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _make_agent(
        monkeypatch,
        ModelCapabilities(
            provider="kimi",
            model="kimi-k2",
            context_window=None,
            max_output_tokens=None,
            source="unknown",
        ),
        provider="kimi",
        model="kimi-k2",
        context_window_override=65_536,
    )

    snapshot = agent.get_context_budget_snapshot()

    assert agent.history_manager.max_tokens == 65_536
    assert snapshot.context_window == 65_536
    assert snapshot.source == "config_override"


def test_context_budget_snapshot_includes_history_system_prompt_and_tool_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _make_agent(
        monkeypatch,
        ModelCapabilities(
            provider="gemini",
            model="gemini-test",
            context_window=8_000,
            max_output_tokens=1_024,
            source="api",
        ),
        max_tokens=900,
    )
    agent.register_tool(
        name="file_read",
        description="Read a file from the workspace",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
            },
            "required": ["path"],
        },
        func=lambda path: path,
    )
    agent.history_manager.add_message(Message.user("Read resume.md and summarize the strongest bullet."))
    agent.history_manager.add_message(Message.assistant("I will inspect the file and summarize the result."))

    history_only_tokens = agent.history_manager.estimated_tokens()
    snapshot = agent.get_context_budget_snapshot()

    assert snapshot.estimated_prompt_tokens > history_only_tokens
    assert snapshot.reserved_output_tokens == 900
    assert snapshot.estimated_remaining_context is not None
    assert snapshot.estimated_remaining_context < snapshot.context_window
