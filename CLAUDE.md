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
3. Register it in the runtime tool wiring used by `ResumeAgent`
4. Add tests in `tests/`

## Conventions

- `snake_case` functions/variables, `PascalCase` classes
- Conventional Commits: `feat:`, `fix:`, `refactor:`, `chore:`, `docs:`
- Fully async agent loop; tools can be sync or async
