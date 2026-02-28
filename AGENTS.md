# AGENTS.md

High-signal instructions for coding agents in this repo. For overview docs, use
`README.md` and `docs/architecture.md`.

## Fast Defaults

- Use `uv` tooling.
- Setup: `uv sync`
- Run CLI: `uv run resume-agent --workspace ./examples/my_resume`
- Validate with targeted tests first, then `uv run pytest`.

## Non-Negotiable Architecture

1. Dependency direction: `cli -> core + tools`, `tools -> domain + core`,
   `core -> domain + providers`.
2. `resume_agent/domain/` must stay pure:
   - no filesystem/network/process I/O
   - no imports from tools/providers
   - return structured dataclasses, not ad-hoc strings
3. `resume_agent/tools/` are adapters that perform I/O and call domain
   functions.

## Change Workflow

- Proceed directly for safe, local edits.
- Ask before destructive operations or broad refactors (large file moves,
  schema/API breaks, command changes with wide blast radius).
- Keep changes minimal and scoped to the request.

## Plan Mode

- Make plans extremely concise; prioritize concision over grammar.
- At the end of each plan, include unresolved questions (if any).

## TDD

- Vertical slices only: one failing test -> implement -> run -> repeat.
- Test behavior through public interfaces only; do not mock internals.
- Mock only system boundaries (external APIs, databases, filesystem, time).
- Before writing any test, confirm with the user which interface and behaviors
  to prioritize.
- Run tests after each RED->GREEN cycle; do not batch.
- Refactor only after all tests pass; do not refactor while any test is failing.

## Security and Data Handling

- Config load order: `config/config.local.yaml` then `config/config.yaml`.
- Keep secrets in local config or environment variables; never commit secrets.
- Do not commit real resume PII or `workspace/sessions/` data.
