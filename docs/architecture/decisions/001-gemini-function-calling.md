# ADR-001: Gemini Function Calling Format Conversion

**Status**: Accepted

**Date**: 2024-01 (retroactive documentation)

**Path Update** (2026-02-16): implementation moved from legacy `resume_agent/*` to `apps/*` + `packages/*`.

## Context

Resume-agent uses Google Gemini API for LLM capabilities with function calling. The codebase needed to support multiple LLM providers while maintaining a consistent tool interface.

Two competing approaches:
1. Define tools in Gemini's native `types.Schema` format
2. Define tools in OpenAI format and convert at runtime

## Decision

We define tool parameters in **OpenAI format** (`tools/base.py:to_schema()`) and convert them to **Gemini `types.Schema` format** when registering with `GeminiAgent.register_tool()`.

History is maintained as `list[types.Content]`. Function responses must be wrapped in `types.Part.from_function_response()`.

## Consequences

### Positive
- **Provider flexibility**: Tools are defined in a widely-adopted format (OpenAI schema)
- **Future compatibility**: Easier to add OpenAI-compatible providers (Kimi, DeepSeek, GLM, MiniMax)
- **Familiar schema**: Most developers know OpenAI's function calling format

### Negative
- **Conversion overhead**: Runtime conversion adds complexity in `agent.py` and `agent_factory.py`
- **Two formats in codebase**: Developers must understand both OpenAI and Gemini formats
- **History management complexity**: Gemini requires function call/response pairs to be adjacent, enforced by `HistoryManager._fix_broken_pairs()`

### Critical Gotcha
Breaking function call/response pairs in history causes Gemini API errors. The `HistoryManager` in `llm.py` implements pair-aware pruning to prevent this.

## Alternatives Considered

1. **Native Gemini format everywhere**: Would lock us into Gemini, making multi-provider support harder
2. **Abstraction layer**: Would add another layer of indirection without clear benefits

## References
- `packages/core/resume_agent_core/tools/base.py` - Tool schema definition
- `packages/core/resume_agent_core/llm.py` - HistoryManager with pair-aware pruning
- `packages/core/resume_agent_core/agent.py` - Format conversion in `_register_tools()`
