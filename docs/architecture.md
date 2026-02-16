# Architecture Map

This document is the high-level system map for contributors and agents.
Deep design details stay in specialized docs under `docs/architecture/`.

## System Overview

The repository has one core runtime and multiple entry adapters:

1. CLI adapter (`resume_agent/cli.py`)
2. Web/API adapter (source: `apps/api/*`, compatibility path: `resume_agent/web/*`)
3. Core runtime (`resume_agent/llm.py`, `resume_agent/agent.py`, `resume_agent/agent_factory.py`; mirrored target: `packages/core/*`)
4. Domain tools (`resume_agent/tools/*`)
5. Multi-agent orchestration (`resume_agent/agents/*`)
6. Provider adapters (`resume_agent/providers/*`, mirrored target: `packages/providers/*`)
7. Shared contracts (`resume_agent/contracts/*`, mirrored target: `packages/contracts/*`)

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

## Runtime Paths

### CLI Path

`cli.py` -> `agent_factory.py` -> `ResumeAgent`/`OrchestratorAgent` -> `LLMAgent` -> tools/providers.

### Web Path

`apps/api/resume_agent_api/app.py` (compat: `resume_agent/web/app.py`) -> API routers -> `InMemoryRuntimeStore` -> workspace/artifact providers + runtime control.

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
