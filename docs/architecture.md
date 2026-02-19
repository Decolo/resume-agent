# Architecture Map

This document is the high-level system map for contributors and agents.
Deep design details stay in specialized docs under `docs/architecture/`.

## System Overview

The repository has one core runtime and multiple entry adapters:

1. CLI adapter (`apps/cli/resume_agent_cli/*`)
2. Web/API adapter (`apps/api/resume_agent_api/*`)
3. Web static assets (`apps/web/ui/*`)
4. Core runtime (`packages/core/resume_agent_core/*`)
5. Provider adapters (`packages/providers/resume_agent_providers/*`)
6. Shared contracts (`packages/contracts/resume_agent_contracts/*`)

## Dependency Direction

Intended direction:

1. `web`/`cli` adapters -> core runtime
2. core runtime -> tools/providers/agents
3. providers -> external SDKs only
4. providers must not depend on app/web/tool layers
5. `packages/*` (monorepo slices) must not depend on `apps/*`

Automated boundary checks:

- `tests/test_architecture_boundaries.py`
- `tests/test_ci_guardrails.py`
- `tests/test_shim_retirement_guardrails.py`

## Runtime Paths

### CLI Path

`apps/cli/resume_agent_cli/app.py` -> `packages/core/resume_agent_core/agent_factory.py` -> `ResumeAgent`/`OrchestratorAgent` -> `LLMAgent` -> tools/providers.

### Web Path

`apps/api/resume_agent_api/app.py` -> API routers -> `InMemoryRuntimeStore` -> workspace/artifact providers + runtime control. Static UI assets are served from `apps/web/ui`.

## Key Constraints

1. Write-like actions require approval flow unless auto-approve is enabled.
2. Session/run lifecycle must remain deterministic (`queued/running/waiting_approval/...`).
3. API contracts are versioned in `docs/api-reference/`.
4. CI quality gates (`test`, `lint`, `typecheck`) are required for merge to `main`.

## Related Docs

1. `docs/architecture/run-state-machine.md`
2. `docs/api-reference/web-api-v1.md`
3. `docs/ops/branch-protection.md`
4. `docs/ops/release-gates.md`
