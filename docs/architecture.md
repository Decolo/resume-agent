# Architecture Map

This document is the high-level system map for contributors and agents.
Deep design details stay in specialized docs under `docs/architecture/`.

## System Overview

Single `resume_agent/` package with logical submodules:

1. **CLI** - Entry point (`resume_agent/cli/`)
2. **Domain** - Pure business logic (`resume_agent/domain/`)
   - Resume parsing, linting, job matching, validation
   - Pure functions with no external dependencies
3. **Core** - Agent runtime (`resume_agent/core/`)
   - LLM orchestration, multi-agent system, session management
4. **Tools** - Tool adapters (`resume_agent/tools/`)
   - File I/O, bash execution, resume tools
5. **Providers** - LLM provider adapters (`resume_agent/providers/`)

## Dependency Direction

1. `cli` → `core` + `tools`
2. `tools` → `domain` + `core`
3. `core` → `domain` + `providers`
4. `domain` → no dependencies (pure functions)
5. `providers` → no dependencies

Automated boundary checks: `tests/architecture/`

## Runtime Paths

### CLI Path

`resume_agent/cli/app.py` → `resume_agent/core/agent_factory.py` → `ResumeAgent`/`OrchestratorAgent` → `LLMAgent` → CLI tools → domain functions.

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

## Related Docs

1. `CLAUDE.md` - Development guide for Claude Code
