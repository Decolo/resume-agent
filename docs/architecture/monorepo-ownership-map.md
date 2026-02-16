# Monorepo Ownership Map (Phase 0 Artifact)

This map defines where current modules should live in the target modular monorepo.
Use this as the source when planning migration PR slices.

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

## Current -> Target Mapping

| Current Path | Target Ownership | Notes |
|---|---|---|
| `resume_agent/cli.py` | `apps/cli` | Keep command compatibility alias during migration |
| `resume_agent/web/*` | `apps/api` + `apps/web` | Python API stays in `apps/api`; static UI artifacts move to `apps/web` |
| `resume_agent/agent.py` | `packages/core` | Runtime entry wrapper can remain for compatibility |
| `resume_agent/agent_factory.py` | `packages/core` | Agent composition layer |
| `resume_agent/llm.py` | `packages/core` | Tool loop + orchestration |
| `resume_agent/session.py` | `packages/core` | Session lifecycle; later can split persistence adapters |
| `resume_agent/tools/*` | `packages/core` | Domain tool runtime capabilities |
| `resume_agent/agents/*` | `packages/core` | Multi-agent protocol/orchestration |
| `resume_agent/providers/*` | `packages/providers` | SDK adapters; keep isolated from app layers |
| `docs/api-reference/*` schemas | `packages/contracts` | Contracts become importable schema module over time |
| `tests/test_web_api_week1.py` | `tests/api` | Move after app split |
| `tests/test_*` (runtime/tool) | `tests/core` | Re-home by domain after structure split |

## Migration Slice Strategy

Use small slices; one slice per PR:

1. **Slice A**: introduce `packages/contracts` and move shared schema constants/types only.
2. **Slice B**: introduce `packages/providers` wrappers and keep compatibility re-exports.
3. **Slice C**: extract `packages/core` with shims in `resume_agent/*`.
4. **Slice D**: relocate API app entrypoints to `apps/api` with compatibility runner. (completed 2026-02-16)
5. **Slice E**: relocate CLI app entrypoint to `apps/cli`. (completed 2026-02-16)
6. **Slice F**: relocate static web UI to `apps/web`. (completed 2026-02-16)

## Guardrails Per Slice

For each slice PR:

1. `uv run --extra dev ruff check .`
2. `uv run --extra dev mypy`
3. `env -u all_proxy -u http_proxy -u https_proxy uv run --extra dev pytest -q`
4. `./scripts/release_gates.sh` if runtime/API touched
5. no new architecture-boundary violations

## Compatibility Policy

During migration window:

1. Keep old import paths as thin forwarding shims.
2. Emit deprecation notes in docs, not runtime hard failures.
3. Remove compatibility shims only after one stable cycle.
