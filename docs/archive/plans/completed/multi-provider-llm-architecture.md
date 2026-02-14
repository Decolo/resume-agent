# Multi-Provider LLM Architecture

## Context

Currently all LLM calls hardcoded to Google Gemini via `google-genai` SDK. `GeminiAgent` in `llm.py` owns history, tool registration, API calls, and Gemini-specific type conversions (`types.Content`, `types.Part`, `types.Schema`). To support multiple providers (cost, stability, quality reasons), we need to extract a provider abstraction layer.

Target providers: Gemini, GLM (智谱), MiniMax, Kimi (Moonshot), DeepSeek (optional).
Key insight: GLM, Kimi, DeepSeek, MiniMax all use OpenAI-compatible APIs. So we need 2 provider implementations: `GeminiProvider` + `OpenAICompatibleProvider`.

Decision log:
- HTTP client: use `openai` Python SDK (following Kimi CLI / OpenCode pattern — native SDK per provider, `openai` SDK with custom `base_url` for compatible providers)
- DeepSeek: included but optional — strong at coding, but for resume writing the key factors are structured response quality and long context window
- Streaming: implement in this phase — all 4 researched projects (Vercel AI SDK, Kimi CLI, Pi-Mono, OpenCode) treat streaming as first-class

## Plan

### Step 1: Create unified message types

New file: `resume_agent/providers/types.py`

```python
@dataclass
class FunctionCall:
    name: str
    arguments: Dict[str, Any]
    id: Optional[str] = None  # required by OpenAI-compat, auto-generated UUID; ignored by Gemini

@dataclass
class FunctionResponse:
    name: str
    response: Dict[str, Any]
    call_id: Optional[str] = None  # matches FunctionCall.id

@dataclass
class MessagePart:
    text: Optional[str] = None
    function_call: Optional[FunctionCall] = None
    function_response: Optional[FunctionResponse] = None

@dataclass
class Message:
    role: str  # "user" | "assistant" | "tool"
    parts: List[MessagePart]
    # convenience constructors: user(), assistant(), assistant_tool_calls(), tool_response()

@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema (OpenAI format — already what BaseTool uses)

@dataclass
class StreamDelta:
    """Single chunk from streaming response."""
    text: Optional[str] = None
    function_call_start: Optional[FunctionCall] = None  # name + partial args
    function_call_delta: Optional[str] = None           # argument JSON fragment
    function_call_end: bool = False
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None

@dataclass
class LLMResponse:
    text: str
    function_calls: List[FunctionCall]
    usage: Optional[Dict[str, int]] = None
    raw: Any = None
```

### Step 2: Create ChatProvider protocol

New file: `resume_agent/providers/base.py`

```python
class ChatProvider(Protocol):
    async def generate(
        self, messages: List[Message], tools: Optional[List[ToolSchema]],
        system_prompt: str, max_tokens: int, temperature: float,
    ) -> LLMResponse: ...

    async def generate_stream(
        self, messages: List[Message], tools: Optional[List[ToolSchema]],
        system_prompt: str, max_tokens: int, temperature: float,
    ) -> AsyncIterator[StreamDelta]: ...
```

### Step 3: Implement GeminiProvider

New file: `resume_agent/providers/gemini.py`

Extract from current `llm.py`:
- `genai.Client` init + API key resolution (env var: `GEMINI_API_KEY`)
- `register_tool()` type conversion logic (OpenAI JSON Schema → `types.Schema`) → `_to_gemini_tools()`
- `_call_llm()` → `generate()` (uses `asyncio.to_thread` wrapping `client.models.generate_content`)
- `_parse_response()` → `_from_gemini_response()` → returns `LLMResponse`
- New: `_to_gemini_contents(messages)` converts `List[Message]` → `List[types.Content]` (role mapping: `"assistant"` → `"model"`, `"tool"` → `"user"` with function_response parts)
- `generate_stream()`: uses `client.models.generate_content_stream()`, yields `StreamDelta`
- Keeps `search_grounding` as Gemini-specific feature

### Step 4: Implement OpenAICompatibleProvider

New file: `resume_agent/providers/openai_compat.py`

Uses `openai.AsyncOpenAI(api_key=..., base_url=...)`:
- `generate()`: calls `client.chat.completions.create(stream=False, ...)`
- `generate_stream()`: calls `client.chat.completions.create(stream=True, ...)`, yields `StreamDelta`
- `_to_openai_messages(messages, system_prompt)` → OpenAI chat format
- `_to_openai_tools(tools)` → OpenAI function calling format (trivial — our schema is already OpenAI format)
- `_parse_response(completion)` → `LLMResponse`
- Auto-generates `tool_call_id` (UUID) for pairing calls/responses

### Step 5: Provider factory + defaults

New file: `resume_agent/providers/__init__.py`

```python
PROVIDER_DEFAULTS = {
    "gemini":   {"api_base": "",                                      "env_key": "GEMINI_API_KEY"},
    "glm":      {"api_base": "https://open.bigmodel.cn/api/paas/v4", "env_key": "GLM_API_KEY"},
    "kimi":     {"api_base": "https://api.moonshot.cn/v1",            "env_key": "KIMI_API_KEY"},
    "deepseek": {"api_base": "https://api.deepseek.com",             "env_key": "DEEPSEEK_API_KEY"},
    "minimax":  {"api_base": "https://api.minimax.chat/v1",          "env_key": "MINIMAX_API_KEY"},
}

def create_provider(provider, api_key, model, api_base="", **kwargs) -> ChatProvider:
    if provider == "gemini":
        return GeminiProvider(api_key, model, api_base, **kwargs)
    else:
        defaults = PROVIDER_DEFAULTS.get(provider, {})
        return OpenAICompatibleProvider(api_key, model, api_base or defaults.get("api_base", ""))
```

### Step 6: Refactor `llm.py`

**HistoryManager**: `List[types.Content]` → `List[Message]`
- Pair-aware pruning logic stays identical, operates on `Message` attributes
- Role checks: `"assistant"` (was `"model"`), check `role == "tool"` (was checking `role == "user"` with function_response parts)
- `_estimate_tokens()`: same heuristic, adapted to `MessagePart` fields

**GeminiAgent → LLMAgent**:
- Inject `ChatProvider` instead of creating `genai.Client`
- `register_tool()`: stores `ToolSchema` directly — no Gemini type conversion
- `_call_llm()`: `self.provider.generate(messages, tools, ...)` → `LLMResponse`
- `_call_llm_stream()`: new method, `self.provider.generate_stream(...)` → `AsyncIterator[StreamDelta]`
- `_parse_response()`: simplified — reads `LLMResponse.function_calls` and `.text` directly
- `_execute_tool()`: returns `Message` (tool_response) instead of `types.Part.from_function_response()`
- Tool responses: `Message(role="tool", ...)` instead of `types.Content(role="user", parts=[...])`
- `run()` loop: add `stream: bool = False` parameter. When True, use `_call_llm_stream()` and yield deltas to caller via callback or async generator
- Keep `GeminiAgent = LLMAgent` alias for backward compat
- `LLMConfig`: add `provider: str = "gemini"` field
- `load_config()`: reads `provider` from YAML
- `_resolve_api_key()`: uses `PROVIDER_DEFAULTS[provider]["env_key"]`

### Step 7: Update `session.py`

- `serialize_message()`: `Message` → dict (simpler — our own dataclass, not Gemini types)
- `deserialize_message()`: dict → `Message`
- Remove `from google.genai import types`, import `Message` from `providers.types`

### Step 8: Update `agent.py`

- Import `LLMAgent` (not `GeminiAgent`), import `create_provider`
- `ResumeAgent.__init__()`: `create_provider(config)` → `LLMAgent(provider=..., config=...)`
- `_register_tools()`: simplified, no Gemini conversion

### Step 9: Update `agent_factory.py`

- All `_create_*_agent()`: `create_provider()` → `LLMAgent(provider=...)`
- Per-agent config can specify `provider` + `api_key` + `model` (falls back to top-level)
- `IntentRouter`: uses `create_provider()` + `LLMAgent`
- Type hints: `GeminiAgent` → `LLMAgent`

### Step 10: Update `cli.py`

- History export/display: `Message.parts` instead of `types.Content.parts`
- Import changes

### Step 11: Config changes

`config/config.yaml`:
```yaml
provider: "gemini"  # "gemini" | "glm" | "kimi" | "deepseek" | "minimax"
api_key: "${GEMINI_API_KEY}"
model: "gemini-3-pro-preview"
```

Per-agent override (optional, falls back to top-level):
```yaml
multi_agent:
  agents:
    parser:
      provider: "deepseek"
      api_key: "${DEEPSEEK_API_KEY}"
      model: "deepseek-chat"
```

### Step 12: Dependencies

`pyproject.toml`: add `openai>=1.0.0` and `httpx>=0.27.0` (openai SDK depends on httpx).

## Files to modify

| File | Change |
|------|--------|
| `resume_agent/providers/__init__.py` | NEW — factory + defaults |
| `resume_agent/providers/types.py` | NEW — Message, FunctionCall, ToolSchema, LLMResponse, StreamDelta |
| `resume_agent/providers/base.py` | NEW — ChatProvider protocol |
| `resume_agent/providers/gemini.py` | NEW — extract from llm.py |
| `resume_agent/providers/openai_compat.py` | NEW — OpenAI-compatible provider |
| `resume_agent/llm.py` | MAJOR — GeminiAgent→LLMAgent, Message types, provider injection, streaming support |
| `resume_agent/session.py` | MODERATE — serialize Message instead of types.Content |
| `resume_agent/agent.py` | MODERATE — use create_provider + LLMAgent |
| `resume_agent/agent_factory.py` | MODERATE — per-agent provider creation |
| `resume_agent/cli.py` | MINOR — Message attribute access |
| `resume_agent/agents/*.py` | MINOR — type hint GeminiAgent→LLMAgent |
| `config/config.yaml` | MINOR — add provider field |
| `pyproject.toml` | MINOR — add openai, httpx |

## Verification

1. `uv run pytest` — all existing tests pass
2. `provider: "gemini"` → agent works exactly as before (regression test)
3. `provider: "deepseek"` with `DEEPSEEK_API_KEY` → agent works with DeepSeek
4. Mixed providers in multi-agent mode (e.g., orchestrator=gemini, parser=deepseek) → delegation works
5. Streaming mode: `run(stream=True)` produces incremental output
6. Session save/load round-trip with new Message format
7. `/export` in CLI still produces correct output
