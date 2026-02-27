"""Provider normalization and streaming regression tests."""

from types import SimpleNamespace

import pytest

from resume_agent.core.llm import LLMAgent, LLMConfig
from resume_agent.providers.gemini import GeminiProvider
from resume_agent.providers.openai_compat import OpenAICompatibleProvider
from resume_agent.providers.types import FunctionCall, GenerationConfig, StreamDelta


def test_gemini_completion_normalizes_text_and_tool_calls():
    provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")

    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(text="hello", function_call=None),
                        SimpleNamespace(
                            text=None, function_call=SimpleNamespace(name="file_read", args={"path": "a.md"})
                        ),
                        SimpleNamespace(text="world", function_call=None),
                    ]
                )
            )
        ]
    )

    normalized = provider._from_gemini_response(response)
    assert normalized.text == "hello world"
    assert len(normalized.function_calls) == 1
    assert normalized.function_calls[0].name == "file_read"
    assert normalized.function_calls[0].arguments == {"path": "a.md"}


def test_gemini_stream_deltas_normalize_text_and_function_call_start():
    provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")
    chunk = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(text="partial", function_call=None),
                        SimpleNamespace(
                            text=None, function_call=SimpleNamespace(name="file_write", args={"path": "b.md"})
                        ),
                    ]
                )
            )
        ]
    )

    deltas = provider._iter_stream_deltas(chunk)
    assert len(deltas) == 2
    assert deltas[0].text == "partial"
    assert deltas[1].function_call_start is not None
    assert deltas[1].function_call_start.name == "file_write"
    assert deltas[1].function_call_start.arguments == {"path": "b.md"}


def test_openai_completion_normalizes_list_content_and_tool_calls():
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model="kimi-k2",
        api_base="https://api.moonshot.cn/v1",
    )

    completion = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=[
                        {"type": "text", "text": "hello "},
                        {"type": "text", "text": "world"},
                    ],
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            function=SimpleNamespace(
                                name="file_read",
                                arguments='{"path":"resume.md"}',
                            ),
                        )
                    ],
                )
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30),
    )

    response = provider._from_openai_completion(completion)

    assert response.text == "hello world"
    assert len(response.function_calls) == 1
    assert response.function_calls[0].name == "file_read"
    assert response.function_calls[0].arguments == {"path": "resume.md"}
    assert response.usage == {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}


def test_openai_stream_delta_keeps_tool_call_id_by_index():
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model="kimi-k2",
        api_base="https://api.moonshot.cn/v1",
    )
    call_ids_by_index = {}

    # First chunk introduces IDs and starts both tool calls.
    chunk1 = SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            index=0,
                            id="call_1",
                            function=SimpleNamespace(name="file_read", arguments='{"path":"a'),
                        ),
                        SimpleNamespace(
                            index=1,
                            id="call_2",
                            function=SimpleNamespace(name="file_write", arguments='{"path":"b'),
                        ),
                    ],
                ),
                finish_reason=None,
            )
        ]
    )
    provider._iter_stream_deltas(chunk1, call_ids_by_index)

    # Second chunk omits IDs but keeps index; provider should recover IDs.
    chunk2 = SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            index=0,
                            id=None,
                            function=SimpleNamespace(name=None, arguments='"}'),
                        ),
                        SimpleNamespace(
                            index=1,
                            id=None,
                            function=SimpleNamespace(name=None, arguments='"}'),
                        ),
                    ],
                ),
                finish_reason="tool_calls",
            )
        ]
    )
    deltas = provider._iter_stream_deltas(chunk2, call_ids_by_index)

    arg_deltas = [d for d in deltas if d.function_call_delta]
    assert len(arg_deltas) == 2
    assert arg_deltas[0].function_call_id == "call_1"
    assert arg_deltas[1].function_call_id == "call_2"


def test_openai_kwargs_use_configured_temperature_by_default():
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model="kimi-k2.5",
        api_base="https://api.moonshot.cn/v1",
    )
    kwargs = provider._build_chat_kwargs(
        messages=[{"role": "user", "content": "hello"}],
        tools=None,
        config=GenerationConfig(system_prompt="", max_tokens=128, temperature=0.2),
        stream=False,
    )

    assert kwargs["temperature"] == 0.2


def test_openai_kwargs_disable_thinking_for_kimi_tool_calls():
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model="kimi-k2.5",
        api_base="https://api.moonshot.cn/v1",
    )
    kwargs = provider._build_chat_kwargs(
        messages=[{"role": "user", "content": "hello"}],
        tools=[{"type": "function", "function": {"name": "file_read", "parameters": {}}}],
        config=GenerationConfig(system_prompt="", max_tokens=128, temperature=1.0),
        stream=False,
    )

    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


def test_openai_kwargs_do_not_force_thinking_for_non_kimi_models():
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model="gpt-4o-mini",
        api_base="https://api.openai.com/v1",
    )
    kwargs = provider._build_chat_kwargs(
        messages=[{"role": "user", "content": "hello"}],
        tools=[{"type": "function", "function": {"name": "file_read", "parameters": {}}}],
        config=GenerationConfig(system_prompt="", max_tokens=128, temperature=0.2),
        stream=False,
    )

    assert "extra_body" not in kwargs


def test_extract_allowed_temperature_from_error_message():
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model="kimi-k2.5",
        api_base="https://api.moonshot.cn/v1",
    )
    error = RuntimeError(
        "Error code: 400 - {'error': {'message': 'invalid temperature: only 0.6 is allowed for this model'}}"
    )
    assert provider._extract_allowed_temperature(error) == 0.6


@pytest.mark.asyncio
async def test_openai_temperature_retry_persists_allowed_temperature(monkeypatch):
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model="kimi-k2.5",
        api_base="https://api.moonshot.cn/v1",
    )
    calls = {"count": 0}

    async def fake_create(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError(
                "Error code: 400 - {'error': {'message': 'invalid temperature: only 0.6 is allowed for this model'}}"
            )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))], usage=None
        )

    monkeypatch.setattr(provider.client.chat.completions, "create", fake_create)

    first_kwargs = provider._build_chat_kwargs(
        messages=[{"role": "user", "content": "hello"}],
        tools=None,
        config=GenerationConfig(system_prompt="", max_tokens=128, temperature=0.2),
        stream=False,
    )
    await provider._create_with_temperature_retry(first_kwargs)
    assert calls["count"] == 2

    second_kwargs = provider._build_chat_kwargs(
        messages=[{"role": "user", "content": "hello"}],
        tools=None,
        config=GenerationConfig(system_prompt="", max_tokens=128, temperature=0.2),
        stream=False,
    )
    assert second_kwargs["temperature"] == 0.6


@pytest.mark.asyncio
async def test_llm_stream_reconstructs_multiple_interleaved_tool_calls():
    class FakeProvider:
        async def generate(self, messages, tools, config):
            raise AssertionError("generate should not be called in this test")

        async def generate_stream(self, messages, tools, config):
            yield StreamDelta(
                function_call_start=FunctionCall(name="file_read", arguments={}, id="call_1"),
                function_call_id="call_1",
                function_call_index=0,
            )
            yield StreamDelta(
                function_call_start=FunctionCall(name="file_write", arguments={}, id="call_2"),
                function_call_id="call_2",
                function_call_index=1,
            )
            yield StreamDelta(function_call_delta='{"path":"a', function_call_id="call_1", function_call_index=0)
            yield StreamDelta(function_call_delta='{"path":"b', function_call_id="call_2", function_call_index=1)
            yield StreamDelta(function_call_delta='"}', function_call_id="call_1", function_call_index=0)
            yield StreamDelta(function_call_delta='"}', function_call_id="call_2", function_call_index=1)

    agent = LLMAgent(
        LLMConfig(
            api_key="test-key",
            provider="kimi",
            model="kimi-k2",
            api_base="https://api.moonshot.cn/v1",
        )
    )
    agent.provider = FakeProvider()

    response = await agent._call_llm_stream()

    assert len(response.function_calls) == 2
    assert response.function_calls[0].name == "file_read"
    assert response.function_calls[0].arguments == {"path": "a"}
    assert response.function_calls[1].name == "file_write"
    assert response.function_calls[1].arguments == {"path": "b"}


@pytest.mark.asyncio
async def test_llm_stream_normalizes_cumulative_text_deltas_for_callback_and_response():
    class FakeProvider:
        async def generate(self, messages, tools, config):
            raise AssertionError("generate should not be called in this test")

        async def generate_stream(self, messages, tools, config):
            # Simulate cumulative snapshots some OpenAI-compatible providers emit.
            yield StreamDelta(text="谢谢你的认可！😊")
            yield StreamDelta(text="谢谢你的认可！😊\n确实，那些都是小修小补的问题。")
            yield StreamDelta(text="谢谢你的认可！😊\n确实，那些都是小修小补的问题。\n你想怎么处理？")

    agent = LLMAgent(
        LLMConfig(
            api_key="test-key",
            provider="kimi",
            model="kimi-k2",
            api_base="https://api.moonshot.cn/v1",
        )
    )
    agent.provider = FakeProvider()

    callback_text_parts: list[str] = []

    def on_stream_delta(delta: StreamDelta) -> None:
        if delta.text:
            callback_text_parts.append(delta.text)

    response = await agent._call_llm_stream(on_stream_delta=on_stream_delta)

    assert callback_text_parts == [
        "谢谢你的认可！😊",
        "\n确实，那些都是小修小补的问题。",
        "\n你想怎么处理？",
    ]
    assert response.text == "谢谢你的认可！😊\n确实，那些都是小修小补的问题。\n你想怎么处理？"
