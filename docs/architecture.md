# Architecture Map

This document is the high-level system map for contributors and agents.
Deep design details stay in specialized docs under `docs/architecture/`.

## System Overview

The repository follows a clean architecture with domain-driven design:

1. **Apps** - Entry points for different environments
   - CLI adapter (`apps/cli/resume_agent_cli/*`)
   - Next.js web app (`apps/web-next/*`) - Full-stack TypeScript with Cloudflare deployment
2. **Domain** - Pure business logic (`packages/domain/resume_agent_domain/*`)
   - Resume parsing, ATS scoring, job matching, validation
   - Pure functions with no external dependencies
3. **Core** - Agent runtime (`packages/core/resume_agent_core/*`)
   - LLM orchestration, multi-agent system, session management
4. **Tools** - Environment-specific adapters
   - CLI tools (`packages/tools/cli/*`) - File I/O, bash execution
   - Web tools (`packages/tools/web/*`) - JSON updates, export, analysis
5. **Providers** - LLM provider adapters (`packages/providers/resume_agent_providers/*`)
6. **Contracts** - Shared types (`packages/contracts/resume_agent_contracts/*`)

## Dependency Direction

Intended direction:

1. `apps/*` -> `packages/core` + `packages/tools/*`
2. `packages/tools/*` -> `packages/domain` + `packages/core`
3. `packages/core` -> `packages/providers`
4. `packages/domain` -> no dependencies (pure functions)
5. `packages/*` must not depend on `apps/*`

Automated boundary checks:

- `tests/test_architecture_boundaries.py`
- `tests/test_ci_guardrails.py`

## Runtime Paths

### CLI Path

`apps/cli/resume_agent_cli/app.py` -> `packages/core/resume_agent_core/agent_factory.py` -> `ResumeAgent`/`OrchestratorAgent` -> `LLMAgent` -> CLI tools -> domain functions.

### Web Path

`apps/web-next/` (Next.js App Router):
- Frontend: React components with Vercel AI SDK for streaming
- API Routes: `/api/chat`, `/api/sessions`, `/api/files`
- Backend: Cloudflare D1 (SQLite) + R2 (object storage)
- Tools: Web-specific tools call domain functions, return structured JSON

## Key Design Decisions

### Architecture Refactoring (2026-02-23)

**Problem**: Original monolithic structure mixed domain logic with infrastructure.

**Solution**: Extracted into layered architecture:
- **Domain layer**: Pure functions (resume_parser, ats_scorer, job_matcher, etc.)
- **Tools layer**: Separate CLI and Web tool implementations
  - CLI: File-based operations (read/write entire files)
  - Web: API-based operations (JSON path updates, structured responses)
- **Core layer**: Infrastructure only (agent loop, LLM integration, caching)

**Benefits**:
- Domain logic is testable without LLM/file system
- CLI and Web can use different tool semantics
- Clear separation of concerns

### Web Stack Migration (2026-02-23)

**From**: Python FastAPI + static HTML
**To**: Next.js 16 (App Router) + Vercel AI SDK v6

**Rationale**:
- Cloudflare Pages deployment (D1 + R2 + KV)
- Multi-provider LLM support (OpenAI, Gemini, Kimi/Moonshot)
- Modern React with streaming UI
- Type-safe full-stack TypeScript

## Key Constraints

1. Domain functions must remain pure (no side effects, no external dependencies)
2. Tools are the only layer that performs I/O or calls external services
3. CLI and Web tools can have different semantics for the same domain operation
4. Session/run lifecycle must remain deterministic
5. CI quality gates (`test`, `lint`, `typecheck`) are required for merge to `main`

## Related Docs

1. `docs/architecture/monorepo-ownership-map.md`
2. `.claude/CLAUDE.md` - Development guide for Claude Code
3. `/tmp/refactoring_final_report.md` - Architecture refactoring details
4. `apps/web-next/README.md` - Next.js app documentation
