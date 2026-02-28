# Execution Data Flow

End-to-end runtime path for the current CLI-first agent.
Use this as the canonical "what runs when" map before changing core behavior.

## High-Level Pipeline (Interactive CLI)

1. CLI entrypoint parses args and loads config:
   - `resume_agent/cli/app.py`
2. Config is validated (provider key/model/workspace checks):
   - `resume_agent/cli/config_validator.py`
3. Runtime dependencies are created:
   - `SessionManager(args.workspace)` in `resume_agent/core/session.py`
   - `create_tools(args.workspace, raw_config)` in `resume_agent/cli/tool_factory.py`
4. Agent mode is resolved:
   - forced single (`--single-agent`)
   - forced multi (`--multi-agent`)
   - config-driven (`create_agent(...)`)
   - `resume_agent/core/agent_factory.py`
5. Interactive loop reads user input and dispatches:
   - `run_interactive()` in `resume_agent/cli/app.py`
6. User prompt executes through `agent.run(...)`:
   - single: `ResumeAgent.run()` in `resume_agent/core/agent.py`
   - multi: `OrchestratorAgent.run()` in `resume_agent/core/agents/orchestrator_agent.py`
   - auto: `AutoAgent.run()` in `resume_agent/core/agent_factory.py`
7. Core LLM loop executes:
   - `LLMAgent.run()` in `resume_agent/core/llm.py`
8. Provider request/response translation:
   - `resume_agent/providers/gemini.py`
   - `resume_agent/providers/openai_compat.py`
9. Tool calls execute (possibly parallel), then results return to LLM loop:
   - tools: `resume_agent/tools/*`
   - domain logic: `resume_agent/domain/*`
10. Final text response is rendered in CLI panel and optional approval prompts are shown.

## LLMAgent Loop (Most Important Runtime)

File: `resume_agent/core/llm.py`

Per step:
1. Add user message to `HistoryManager`.
2. Call provider (`generate` or `generate_stream`).
3. Parse into `response_text` + `function_calls`.
4. Append assistant message to history.
5. If no function calls: return final text.
6. If write tools are requested:
   - CLI mode: pause and queue pending approvals.
   - API handler mode: approval callback decides.
7. Execute tool calls concurrently with `asyncio.gather`.
8. Append tool responses to history.
9. Trigger session auto-save when session manager exists.
10. Continue until model returns text-only or max steps hit.

Safety/reliability in this loop:
- loop guard (repeated tool-only cycles)
- retry/backoff wrapper for provider calls
- per-tool caching for read-heavy operations
- observability events for steps, tools, and llm calls

## Tool/Data Path

Tool registration source:
- `resume_agent/cli/tool_factory.py`

Common path for resume operations:
1. LLM chooses tool schema name (for example `resume_parse`).
2. `LLMAgent._execute_tool` resolves function and args.
3. Tool adapter handles I/O and format translation:
   - `resume_agent/tools/resume_tools.py`
4. Adapter calls pure domain function:
   - parser/linter/matcher/writer/validator modules in `resume_agent/domain/`
5. Tool returns `ToolResult`, LLM loop writes `FunctionResponse` back to history.

## Multi-Agent Path (When Enabled)

Factory setup:
- `create_multi_agent_system(...)` in `resume_agent/core/agent_factory.py`

Runtime pattern:
1. Orchestrator LLM receives user task.
2. Orchestrator has "delegate_to_*" tools registered via `AgentTool`.
3. Calling a delegate tool creates an `AgentTask` and routes through `DelegationManager`.
4. Target specialized agent executes via its own `LLMAgent` and tools.
5. Result returns to orchestrator as a tool response.

Key files:
- `resume_agent/core/agents/agent_tool.py`
- `resume_agent/core/agents/delegation.py`
- `resume_agent/core/agents/parser_agent.py`
- `resume_agent/core/agents/writer_agent.py`
- `resume_agent/core/agents/formatter_agent.py`

## Session Persistence Path

Files:
- `resume_agent/core/session.py`
- `resume_agent/cli/app.py`

Behavior:
- Sessions are stored under `<workspace>/sessions/`.
- Tool execution auto-saves conversation/history/observability.
- `/save`, `/load`, `/sessions`, `/delete-session` operate on the same storage/index.

## Suggested Reading Order

If you want to understand execution quickly:
1. `resume_agent/cli/app.py`
2. `resume_agent/core/agent_factory.py`
3. `resume_agent/core/llm.py`
4. `resume_agent/cli/tool_factory.py`
5. `resume_agent/tools/resume_tools.py`
6. `resume_agent/domain/*.py`
7. `resume_agent/providers/*.py`
8. `resume_agent/core/session.py`

If you are debugging multi-agent behavior, add:
1. `resume_agent/core/agents/orchestrator_agent.py`
2. `resume_agent/core/agents/agent_tool.py`
3. `resume_agent/core/agents/delegation.py`
