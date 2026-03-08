# Architecture Map

This document is the high-level system map for contributors and agents.
Deep design details stay in specialized docs under `docs/architecture/`.
Last validated against code: 2026-03-09.

## System Overview

Single `resume_agent/` package with logical submodules:

1. **CLI** - Entry point (`resume_agent/cli/`)
2. **Domain** - Pure business logic (`resume_agent/domain/`)
   - Resume parsing, linting, job matching, validation
   - Pure functions with no external dependencies
3. **Core** - Agent runtime (`resume_agent/core/`)
   - LLM orchestration, multi-agent system, session management
4. **Tools** - Tool adapters (`resume_agent/tools/`)
   - File I/O, bash execution, resume tools, LinkedIn browser automation (CDP), web fetch
5. **Providers** - LLM provider adapters (`resume_agent/providers/`)

## Dependency Direction

1. `cli` → `core` + `tools`
2. `tools` → `domain` + `core`
3. `core` → `domain` + `providers`
4. `domain` → no dependencies (pure functions)
5. `providers` → no dependencies

Automated boundary checks: `tests/architecture/`

## Runtime Paths

### CLI Path (Top-Level)

`resume_agent/cli/app.py` → `resume_agent/core/agent_factory.py` → `ResumeAgent`/`OrchestratorAgent` → `LLMAgent` → CLI tools → domain functions.

### Detailed Execution Flow

For step-by-step runtime behavior (inline wire approval, loop guard, auto-save, delegation), see:

- `docs/architecture/execution-data-flow.md`

## Key Design Decisions

### Architecture Refactoring (2026-02-23)

**Problem**: Original monolithic structure mixed domain logic with infrastructure.

**Solution**: Extracted into layered architecture:
- **Domain layer**: Pure functions (resume_parser, resume_linter, job_matcher, etc.)
- **Tools layer**: Tool adapters wrapping domain functions with file I/O
- **Core layer**: Infrastructure only (agent loop, LLM integration, caching)

### Monorepo Flattening (2026-02-25)

**Problem**: 6 pyproject.toml files for 55 source files after removing web-next.

**Solution**: Flattened into single `resume_agent/` package. Same logical boundaries enforced by architecture tests, but no workspace overhead.

## Key Constraints

1. Domain functions must remain pure (no side effects, no external dependencies)
2. Tools are the only layer that performs I/O or calls external services
3. Session/run lifecycle must remain deterministic
4. CI quality gates (`test`, `lint`, `typecheck`) are required for merge to `main`

## Agent Loop vs Tool Boundary (Mandatory)

Use these rules when deciding where code should live.

1. `LLMAgent` (`resume_agent/core/llm.py`) owns orchestration only:
   - provider call and response normalization
   - history append/prune and step lifecycle
   - approval control flow (`request`/`resolve`)
   - tool dispatch, observability, and session save trigger
2. Tool implementations (`resume_agent/tools/*`) own side effects and mutation semantics:
   - filesystem/network/process I/O
   - domain-specific validation (for example ambiguous edit matches)
   - idempotency and no-op detection
   - approval metadata via `build_approval_request()` (action key + description)
   - optional preview material for approval (for example diffs) via `build_approval_context()`
3. `LLMAgent` must not read or mutate target resources to "simulate" tool behavior.
   - Example: do not read files in loop code to generate write diffs.
   - Instead, call tool hook (`build_approval_context`) and display returned text.
4. Generic policies may stay in loop only if they are tool-agnostic.
   - Allowed: max steps per turn, malformed/empty provider response retries, missing required args.
   - Not allowed: file-specific rewrite guards hardcoded in loop.
5. Cross-tool UX contracts are explicit and structured.
   - If UI needs extra context before approval, expose it from tool layer.
   - Keep loop consumption generic so new mutation tools can reuse the same path.

## Related Docs

1. `docs/architecture/execution-data-flow.md` - End-to-end runtime flow
2. `docs/architecture/adrs/README.md` - ADR index
3. `docs/architecture/adrs/003-agent-loop-tool-boundary.md` - Boundary decision for loop/tool responsibilities
4. `docs/archive/phase1-improvements.md` - Archived phase summary
5. `docs/sessions/session-persistence.md` - Session save/load internals
6. `AGENTS.md` - Cross-agent repository operating constraints
7. `CLAUDE.md` - Claude-specific runtime guidance

## Architecture Doc Freshness

Use this section to avoid starting from stale details when editing docs:

| Document | Status | Notes |
| --- | --- | --- |
| `docs/architecture/execution-data-flow.md` | Current | Canonical runtime behavior for CLI, LLM loop, tools, and delegation. |
| `docs/architecture/adrs/001-gemini-function-calling.md` | Current (updated) | Decision remains valid; references now map to provider-agnostic schema + provider adapter code. |
| `docs/architecture/adrs/002-multi-agent-architecture.md` | Current | Operational mode model remains `single` / `multi` / `auto`. |
| `docs/architecture/adrs/003-agent-loop-tool-boundary.md` | Current | Defines hard ownership boundary between loop orchestration and tool mutation semantics. |
| `docs/archive/phase1-improvements.md` | Archived | Historical implementation summary retained for context only. |

## Resume Lint Path (Current)

For lint-related doc changes, read this path in order:

1. `resume_agent/cli/tool_factory.py` (`lint_resume` registration)
2. `resume_agent/core/agent_factory.py` (single vs multi-agent tool wiring)
3. `resume_agent/tools/resume_tools.py` (`ResumeLinterTool`)
4. `resume_agent/domain/resume_linter.py` (score model + report formatting)
5. `resume_agent/domain/linting/*` (rule engine, AST parser, language router)
