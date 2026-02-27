# Repository Guidelines

## Project Structure & Module Organization

All source lives in a single `resume_agent/` package:

- `resume_agent/cli/` - Interactive CLI with rich terminal UI
- `resume_agent/domain/` - Pure domain logic
  - `resume_parser.py`, `resume_writer.py`, `ats_scorer.py`, `job_matcher.py`, `resume_validator.py`
  - Pure functions with no external dependencies
- `resume_agent/core/` - Agent runtime
  - LLM orchestration, multi-agent system, session management
  - Caching, retry logic, observability
- `resume_agent/tools/` - Tool adapters
  - File I/O, bash execution, resume tools
- `resume_agent/providers/` - LLM provider adapters

### Configuration & Data
- `config/` - Runtime configuration (`config.local.yaml` is default, `config.yaml` is fallback)
- `tests/` - pytest test suites (`tests/cli/`, `tests/core/`, `tests/domain/`, `tests/tools/`, `tests/architecture/`)
- `docs/` - Documentation
- `examples/` - Sample resumes
- `workspace/sessions/` - Runtime session data (gitignored)

## Build, Test, and Development Commands

### Python (CLI)
```bash
# Install dependencies (recommended)
uv sync

# Alternative editable install
pip install -e .

# Run the CLI
uv run resume-agent --workspace ./examples/my_resume

# Run via module
uv run python -m resume_agent.cli.app

# Run tests
uv run pytest
```

## Architecture Principles

### Dependency Direction
1. `cli` → `core` + `tools`
2. `tools` → `domain` + `core`
3. `core` → `domain` + `providers`
4. `domain` → **no dependencies** (pure functions)
5. `providers` → **no dependencies**

### Tool Design Philosophy
- Tools wrap domain functions with file I/O semantics
- Domain functions remain pure (no side effects)

### Domain Layer Rules
- All domain functions must be pure (no side effects, no external dependencies)
- Return structured dataclasses, not strings
- Testable without LLM or file system

## Coding Style & Naming Conventions

### Python
- 4-space indentation
- `snake_case` for functions/variables/modules
- `PascalCase` for classes
- Type hints for public APIs
- Docstrings for public functions

## Testing Guidelines

### Python Tests
- Tests live in `tests/` and use `pytest` with `pytest-asyncio`
- Name tests `test_*.py` with functions `test_*`
- Run: `uv run pytest`

## Commit & Pull Request Guidelines

- Commit messages follow Conventional Commits:
  - `feat:` - New features
  - `fix:` - Bug fixes
  - `refactor:` - Code restructuring
  - `chore:` - Maintenance tasks
  - `docs:` - Documentation updates
- PRs should include:
  - Clear summary of changes
  - Test results
  - Sample outputs for resume formatting changes

## Security & Configuration Notes

- Store API keys in `config/config.local.yaml` or environment variables
- **Never commit secrets**
- Resume files contain PII—avoid committing real resumes
- Session files contain full conversations—do not commit `workspace/sessions/`

## Session Persistence

### CLI Sessions
- Saved as JSON under `workspace/sessions/` with `.index.json`
- Commands: `/save [name]`, `/load <id>`, `/sessions`, `/delete-session <id>`
- Auto-save enabled by default

## Plan Mode

- Make the plan extremely concise. Sacrifice grammar for the sake of concision.
- At the end of each plan, give me a list of unresolved questions to answer, if any.
