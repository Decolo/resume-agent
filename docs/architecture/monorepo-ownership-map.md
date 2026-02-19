# Monorepo Ownership Map

This map defines the current ownership after monorepo cutover.

## Target Topology

```text
apps/
  cli/
  api/
  web/
packages/
  core/
  providers/
  contracts/
```

## Ownership Mapping

| Path | Ownership | Notes |
|---|---|---|
| `apps/cli/resume_agent_cli/*` | `apps/cli` | CLI adapter and command handling |
| `apps/api/resume_agent_api/*` | `apps/api` | FastAPI app, routers, runtime store |
| `apps/web/ui/*` | `apps/web` | Static UI assets |
| `packages/core/resume_agent_core/*` | `packages/core` | Runtime orchestration + tools + multi-agent |
| `packages/providers/resume_agent_providers/*` | `packages/providers` | LLM provider adapters |
| `packages/contracts/resume_agent_contracts/*` | `packages/contracts` | Shared schemas and constants |
| `tests/test_web_api_week1.py` | `tests/api` | Move after app split |
| `tests/test_*` (runtime/tool) | `tests/core` | Re-home by domain after structure split |

## Migration Status

All planned slices A-F are completed as of 2026-02-16.

## Guardrails Per Slice

For each slice PR:

1. `uv run --extra dev ruff check .`
2. `uv run --extra dev mypy`
3. `env -u all_proxy -u http_proxy -u https_proxy uv run --extra dev pytest -q`
4. `./scripts/release_gates.sh` if runtime/API touched
5. no new architecture-boundary violations

## Compatibility Policy

Post-cutover:

1. `apps/*` + `packages/*` are implementation source of truth.
2. Legacy `resume_agent/*` shims are retired.
3. Architecture tests enforce no new imports from `resume_agent.*` in implementation layers.
