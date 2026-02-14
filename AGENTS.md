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


## Skills
A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. Below is the list of skills that can be used. Each entry includes a name, description, and file path so you can open the source for full instructions when using a specific skill.
### Available skills
- skill-creator: Guide for creating effective skills. This skill should be used when users want to create a new skill (or update an existing skill) that extends Codex's capabilities with specialized knowledge, workflows, or tool integrations. (file: /Users/decolo/.codex/skills/.system/skill-creator/SKILL.md)
- skill-installer: Install Codex skills into $CODEX_HOME/skills from a curated list or a GitHub repo path. Use when a user asks to list installable skills, install a curated skill, or install a skill from another repo (including private repos). (file: /Users/decolo/.codex/skills/.system/skill-installer/SKILL.md)
### How to use skills
- Discovery: The list above is the skills available in this session (name + description + file path). Skill bodies live on disk at the listed paths.
- Trigger rules: If the user names a skill (with `$SkillName` or plain text) OR the task clearly matches a skill's description shown above, you must use that skill for that turn. Multiple mentions mean use them all. Do not carry skills across turns unless re-mentioned.
- Missing/blocked: If a named skill isn't in the list or the path can't be read, say so briefly and continue with the best fallback.
- How to use a skill (progressive disclosure):
  1) After deciding to use a skill, open its `SKILL.md`. Read only enough to follow the workflow.
  2) When `SKILL.md` references relative paths (e.g., `scripts/foo.py`), resolve them relative to the skill directory listed above first, and only consider other paths if needed.
  3) If `SKILL.md` points to extra folders such as `references/`, load only the specific files needed for the request; don't bulk-load everything.
  4) If `scripts/` exist, prefer running or patching them instead of retyping large code blocks.
  5) If `assets/` or templates exist, reuse them instead of recreating from scratch.
- Coordination and sequencing:
  - If multiple skills apply, choose the minimal set that covers the request and state the order you'll use them.
  - Announce which skill(s) you're using and why (one short line). If you skip an obvious skill, say why.
- Context hygiene:
  - Keep context small: summarize long sections instead of pasting them; only load extra files when needed.
  - Avoid deep reference-chasing: prefer opening only files directly linked from `SKILL.md` unless you're blocked.
  - When variants exist (frameworks, providers, domains), pick only the relevant reference file(s) and note that choice.
- Safety and fallback: If a skill can't be applied cleanly (missing files, unclear instructions), state the issue, pick the next-best approach, and continue.
