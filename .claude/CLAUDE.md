# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Resume Agent is an AI-powered resume modification tool using Google Gemini API with function calling. Python 3.10+, built with `hatchling`. Parses/analyzes/improves resumes in PDF, DOCX, Markdown, JSON, HTML.

## Development Commands

```bash
# Install
uv sync                    # recommended
pip install -e ".[dev]"    # alternative with dev deps

# Run
uv run resume-agent                          # interactive mode
uv run resume-agent --workspace ./examples/my_resume
uv run resume-agent --prompt "Analyze the resume"  # single prompt
uv run python -m resume_agent.cli            # module mode

# Test
uv run pytest                                # all tests
uv run pytest tests/test_phase1_improvements.py -v                    # one file
uv run pytest tests/test_phase1_improvements.py::TestRetryLogic -v    # one class
uv run pytest --cov=resume_agent --cov-report=html                    # coverage
```

No linter or formatter is configured. Tests use `pytest` + `pytest-asyncio`.

## Architecture

### Three Operational Modes

Controlled by `multi_agent.enabled` in `config/config.local.yaml` (falls back to `config/config.yaml`):

- **`false`** (default): Single-agent mode. `ResumeAgent` (`agent.py`) handles everything directly with all tools.
- **`true`**: Multi-agent mode. `OrchestratorAgent` delegates to `ParserAgent`, `WriterAgent`, `FormatterAgent`.
- **`"auto"`**: `AutoAgent` (`agent_factory.py`) uses `IntentRouter` (LLM classifier) + regex heuristics to route each request to single or multi-agent mode. Routes to multi when: multiple output formats, batch/bulk keywords, or multiple file paths detected.

Entry point: `agent_factory.create_agent()` → returns `ResumeAgent`, `OrchestratorAgent`, or `AutoAgent`.

### Function Calling — Critical Gotcha

Tools define parameters in **OpenAI format** (`tools/base.py:to_schema()`), but `agent.py` and `agent_factory.py` convert them to **Gemini `types.Schema` format** when registering with `GeminiAgent.register_tool()`. History is maintained as `list[types.Content]`. Function responses must be wrapped in `types.Part.from_function_response()`.

**Pair-aware history pruning** (`llm.py:HistoryManager`): Gemini requires function call and function response turns to be adjacent. The pruning logic in `_prune_if_needed()` and `_fix_broken_pairs()` preserves these pairs — breaking them causes API errors.

### Tool System

All tools extend `BaseTool` (`tools/base.py`) and return `ToolResult`. Tools can be sync or async (detected via `asyncio.iscoroutinefunction()`). Independent tool calls execute in parallel via `asyncio.gather()`.

Tools: `file_read`, `file_write`, `file_list`, `file_rename`, `bash`, `resume_parse`, `resume_write`, `web_fetch`, `web_read`.

Each specialized agent gets a restricted subset (least privilege):
- **ParserAgent**: `resume_parse`, `file_read`, `file_list`
- **WriterAgent**: `file_read`, `file_write`
- **FormatterAgent**: `resume_write`, `file_read`, `file_write`
- **OrchestratorAgent**: `file_list`, `file_rename`, `web_read`, `web_fetch` + agent tools via `AgentTool` wrapper

### Multi-Agent Delegation

`agents/protocol.py` defines `AgentTask`/`AgentResult`. `DelegationManager` (`agents/delegation.py`) handles routing with DFS cycle detection and max depth (default 5). `AgentRegistry` scores agents: 50% capability match + 30% success rate + 20% load.

Agents are wrapped as tools using `AgentTool` (`agents/agent_tool.py`) so the orchestrator calls them via the same function calling interface.

Each agent has isolated `HistoryManager` via `MultiAgentHistoryManager` — context is passed explicitly through `AgentTask.context`, not shared history.

### Reliability Stack

- **Retry** (`retry.py`): `retry_with_backoff()` — 3 attempts, 1s base, 2x exponential, ±20% jitter. Classifies `TransientError` vs `PermanentError`.
- **Cache** (`cache.py`): In-memory TTL cache. `file_read` 60s, `file_list` 30s, `resume_parse` 300s. Write tools never cached. SHA256 key generation.
- **Observability** (`observability.py`): `AgentObserver` tracks tool calls, LLM requests, errors, costs. `AgentEvent` for structured logging.

### Session Persistence

`session.py` handles save/load of full agent state (history, observability data, multi-agent state) as JSON under `workspace/sessions/`. Auto-save after tool execution when enabled. CLI commands: `/save`, `/load`, `/sessions`, `/delete-session`, `/auto-save`.

## Configuration

Config loaded from `config/config.local.yaml` (primary) → `config/config.yaml` (fallback). Supports `${ENV_VAR}` substitution. Key env var: `GEMINI_API_KEY`.

## Adding a New Tool

1. Create class in `resume_agent/tools/` extending `BaseTool`
2. Implement `execute()`, define `name`, `description`, `parameters`
3. Register in `ResumeAgent._init_tools()` (single-agent) or via `_register_tools()` in `agent_factory.py` (multi-agent)
4. Add tests in `tests/`

## Adding a New Specialized Agent

1. Create class in `resume_agent/agents/` extending `BaseAgent`
2. Define `agent_id`, `agent_type`, `capabilities`
3. Implement `execute(task)` and `can_handle(task)`
4. Create system prompt in `resume_agent/skills/`
5. Register in `agent_factory.py`

## Conventions

- `snake_case` functions/variables, `PascalCase` classes
- Conventional Commits: `feat:`, `fix:`, `refactor:`, `chore:`, `docs:`
- Fully async agent loop; tools can be sync or async

## Plan Mode

- Make the plan extremely concise. Sacrifice grammar for the sake of concision.
- At the end of each plan, give me a list of unresolved questions to answer, if any.
