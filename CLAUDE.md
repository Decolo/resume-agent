# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language

Default to English for all responses, code comments, and commit messages. Switch to Chinese (中文) only when explaining abstract or conceptually complex ideas that benefit from it.

## Workflow

- For straightforward, low-risk edits, implement directly and explain what changed.
- Ask for confirmation before destructive operations, risky migrations, or broad multi-file refactors.
- When the user asks to review or walk through code/features together: 1) Show visual explanation and core code first, 2) Wait for user feedback, 3) Only proceed to the next item after explicit confirmation.

Config loaded from `config/config.local.yaml` (primary) → `config/config.yaml` (fallback). Supports `${ENV_VAR}` substitution. Key env var: `GEMINI_API_KEY`.

## Adding a New Tool

1. Create class in `resume_agent/tools/` extending `BaseTool`
2. Implement `execute()`, define `name`, `description`, `parameters`
3. Register in `ResumeAgent._register_tools()` (single-agent) or via `_register_tools()` in `core/agent_factory.py` (multi-agent)
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
