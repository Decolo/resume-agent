# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language

Primary languages: Python, TypeScript. Default to English for all responses, code comments, and commit messages. Switch to Chinese (中文) only when explaining abstract or conceptually complex ideas that benefit from it.

## Workflow

- Always explain your plan before making any code changes. Wait for user confirmation before editing files, especially for multi-file changes.
- When the user asks to review or walk through code/features together: 1) Show visual explanation and core code first, 2) Wait for user feedback, 3) Only proceed to the next item after explicit confirmation.
- When a task requires multiple iterations or significant token usage, do NOT pause to warn about time/tokens. Just continue working until the task is complete or the user interrupts.

## Git

For git operations: `git add .` then commit with a concise conventional commit message and push. Do not open PRs unless explicitly asked.

## UI/CSS

When the user references a Figma design, ask for a screenshot or specific values before implementing. Do not guess colors, spacing, or component styling. If a CSS fix isn't working after 2 attempts, stop and explain what's blocking you instead of continuing to iterate blindly.

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
uv run pytest tests/core/test_phase1_improvements.py -v                    # one file
uv run pytest tests/core/test_phase1_improvements.py::TestRetryLogic -v    # one class
uv run pytest --cov=resume_agent --cov-report=html                    # coverage
```

No linter or formatter is configured. Tests use `pytest` + `pytest-asyncio`.

## Architecture

### Three Operational Modes

Controlled by `multi_agent.enabled` in `config/config.local.yaml` (falls back to `config/config.yaml`):

- **`false`** (default): Single-agent mode. `ResumeAgent` (`core/agent.py`) handles everything directly with all tools.
- **`true`**: Multi-agent mode. `OrchestratorAgent` delegates to `ParserAgent`, `WriterAgent`, `FormatterAgent`.
- **`"auto"`**: `AutoAgent` (`core/agent_factory.py`) uses `IntentRouter` (LLM classifier) + regex heuristics to route each request to single or multi-agent mode. Routes to multi when: multiple output formats, batch/bulk keywords, or multiple file paths detected.

Entry point: `core/agent_factory.create_agent()` → returns `ResumeAgent`, `OrchestratorAgent`, or `AutoAgent`.

### Function Calling — Critical Gotcha

Tools define parameters in **OpenAI format** (`core/tools/base.py:to_schema()`), but `core/agent.py` and `core/agent_factory.py` convert them to **Gemini `types.Schema` format** when registering with `GeminiAgent.register_tool()`. History is maintained as `list[types.Content]`. Function responses must be wrapped in `types.Part.from_function_response()`.

**Pair-aware history pruning** (`core/llm.py:HistoryManager`): Gemini requires function call and function response turns to be adjacent. The pruning logic in `_prune_if_needed()` and `_fix_broken_pairs()` preserves these pairs — breaking them causes API errors.

### Tool System

All tools extend `BaseTool` (`core/tools/base.py`) and return `ToolResult`. Tools can be sync or async (detected via `asyncio.iscoroutinefunction()`). Independent tool calls execute in parallel via `asyncio.gather()`.

Tools: `file_read`, `file_write`, `file_list`, `file_rename`, `bash`, `resume_parse`, `resume_write`, `web_fetch`, `web_read`.

Each specialized agent gets a restricted subset (least privilege):
- **ParserAgent**: `resume_parse`, `file_read`, `file_list`
- **WriterAgent**: `file_read`, `file_write`
- **FormatterAgent**: `resume_write`, `file_read`, `file_write`
- **OrchestratorAgent**: `file_list`, `file_rename`, `web_read`, `web_fetch` + agent tools via `AgentTool` wrapper

### Multi-Agent Delegation

`core/agents/protocol.py` defines `AgentTask`/`AgentResult`. `DelegationManager` (`core/agents/delegation.py`) handles routing with DFS cycle detection and max depth (default 5). `AgentRegistry` scores agents: 50% capability match + 30% success rate + 20% load.

Agents are wrapped as tools using `AgentTool` (`core/agents/agent_tool.py`) so the orchestrator calls them via the same function calling interface.

Each agent has isolated `HistoryManager` via `MultiAgentHistoryManager` — context is passed explicitly through `AgentTask.context`, not shared history.

### Reliability Stack

- **Retry** (`core/retry.py`): `retry_with_backoff()` — 3 attempts, 1s base, 2x exponential, ±20% jitter. Classifies `TransientError` vs `PermanentError`.
- **Cache** (`core/cache.py`): In-memory TTL cache. `file_read` 60s, `file_list` 30s, `resume_parse` 300s. Write tools never cached. SHA256 key generation.
- **Observability** (`core/observability.py`): `AgentObserver` tracks tool calls, LLM requests, errors, costs. `AgentEvent` for structured logging.

### Session Persistence

`core/session.py` handles save/load of full agent state (history, observability data, multi-agent state) as JSON under `workspace/sessions/`. Auto-save after tool execution when enabled. CLI commands: `/save`, `/load`, `/sessions`, `/delete-session`, `/auto-save`.

## Configuration

Config loaded from `config/config.local.yaml` (primary) → `config/config.yaml` (fallback). Supports `${ENV_VAR}` substitution. Key env var: `GEMINI_API_KEY`.

## Adding a New Tool

1. Create class in `resume_agent/tools/` extending `BaseTool`
2. Implement `execute()`, define `name`, `description`, `parameters`
3. Register in `ResumeAgent._init_tools()` (single-agent) or via `_register_tools()` in `core/agent_factory.py` (multi-agent)
4. Add tests in `tests/`

## Adding a New Specialized Agent

1. Create class in `resume_agent/core/agents/` extending `BaseAgent`
2. Define `agent_id`, `agent_type`, `capabilities`
3. Implement `execute(task)` and `can_handle(task)`
4. Create system prompt in `resume_agent/core/skills/`
5. Register in `core/agent_factory.py`

## Conventions

- `snake_case` functions/variables, `PascalCase` classes
- Conventional Commits: `feat:`, `fix:`, `refactor:`, `chore:`, `docs:`
- Fully async agent loop; tools can be sync or async

## Plan Mode

- Make the plan extremely concise. Sacrifice grammar for the sake of concision.
- At the end of each plan, give me a list of unresolved questions to answer, if any.
