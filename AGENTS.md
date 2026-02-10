# Repository Guidelines

## Project Structure & Module Organization

- `resume_agent/` holds the application code. Core orchestration lives in `resume_agent/agent.py` and `resume_agent/cli.py`.
- `resume_agent/agents/` contains agent implementations and coordination logic; `resume_agent/tools/` contains tool integrations (file, bash, parser/writer).
- `resume_agent/skills/` stores prompt assets and domain expertise.
- `config/` contains runtime configuration such as `config.local.yaml` (default) and optional `config.yaml`.
- `tests/` contains pytest suites.
- `docs/` and `examples/` contain user guides and sample resumes; `output/` is used for generated artifacts.
- Runtime session data (Phase 3) is stored under `workspace/sessions/` when enabled.

## Build, Test, and Development Commands

```bash
# Install dependencies (recommended)
uv sync

# Alternative editable install
pip install -e .

# Run the CLI with a workspace
uv run resume-agent --workspace ./examples/my_resume

# Run via module
uv run python -m resume_agent.cli

# Helper launcher
./run_agent.sh ./examples/my_resume
```

## Coding Style & Naming Conventions

- Python code uses 4-space indentation and follows existing module structure.
- Prefer `snake_case` for functions/variables, `PascalCase` for classes, and `snake_case` for modules.
- Keep public-facing CLI text concise and user-focused; align new prompts with the tone in `resume_agent/skills/`.

## Testing Guidelines

- Tests live in `tests/` and use `pytest` with `pytest-asyncio` for async coverage.
- Name tests `test_*.py` with functions `test_*`.
- Run the suite with:

```bash
uv run pytest
```

## Commit & Pull Request Guidelines

- Commit messages follow Conventional Commits (e.g., `feat: ...`, `fix: ...`, `refactor: ...`, `chore: ...`).
- PRs should include a clear summary, tests run, and any sample outputs if resume formatting changes (e.g., a snippet from `output/` or `examples/`).

## Security & Configuration Notes

- Store API keys in `config/config.local.yaml` or environment variables; do not commit secrets.
- Resume files often contain PII—avoid committing real resumes and keep generated artifacts out of version control unless explicitly intended.
- Session files may include full conversations and PII; do not commit `workspace/sessions/`.

## Session Persistence (Phase 3)

- Sessions are saved as JSON under `workspace/sessions/` with an index file at `.index.json`.
- CLI commands: `/save [name]`, `/load <id>`, `/sessions`, `/delete-session <id>`.
- Auto-save is always enabled — sessions are saved automatically after tool execution.


## Plan Mode

- Make the plan extremely concise. Sacrifice grammar for the sake of concision.
- At the end of each plan, give me a list of unresolved questions to answer, if any.
