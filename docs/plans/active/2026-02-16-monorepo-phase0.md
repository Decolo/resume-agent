# Monorepo Refactor Phase 0 Plan

Status: in_progress
Owner: decolo
Start: 2026-02-16
Target: 2026-02-23

## Goal

Define a safe migration path to modular monorepo structure while preserving:

1. current CLI local session workflow
2. current web/API behavior
3. CI quality gates and release gates

This phase produces architecture and sequencing only (no large code moves).

## Constraints

1. No production behavior regression.
2. Keep `uv run resume-agent` usable during migration.
3. Keep PR size small and reversible.
4. Keep required checks green (`test`, `lint`, `typecheck`).

## Target Structure (Phase Goal)

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

`apps/*` depend on `packages/*`; `packages` must not depend on `apps`.

## Phase Breakdown

### Phase 0 (this plan)

1. Freeze dependency direction rules (already enforced by architecture tests).
2. Define package ownership map (what files move where).
3. Define compatibility shim strategy to keep existing imports working temporarily.
4. Define per-phase validation matrix and rollback points.

### Phase 1 (minimal extraction)

1. Create `packages/contracts` for shared API/event/session schemas.
2. Create `packages/providers` wrapper boundary around existing provider layer.
3. Keep current runtime path intact via shims.

Exit criteria:

1. all existing tests pass
2. no CLI command breakage
3. no API contract breakage

### Phase 2 (core split)

1. Move agent runtime + tool orchestration into `packages/core`.
2. Leave adapter entrypoints in place (`resume_agent/cli.py`, `resume_agent/web/*`) as thin wrappers.

Exit criteria:

1. release-gate script still passes
2. architecture boundary tests updated and passing

### Phase 3 (app split)

1. Move web/api app scaffolding to `apps/api` and frontend to `apps/web`. (Slice D completed 2026-02-16; frontend pending)
2. Move CLI command app to `apps/cli`.
3. Keep legacy command aliases until one release cycle completes.

Exit criteria:

1. CI stays green
2. migration notes published
3. rollback instructions validated

## Risks and Mitigations

1. Import churn causing breakage:
   - mitigate with temporary compatibility modules and narrow PR slices.
2. Hidden coupling discovered late:
   - mitigate with stricter architecture tests per phase.
3. Developer friction:
   - mitigate with docs and stable local commands during transition.

## Validation Matrix

Run for each migration PR:

1. `uv run --extra dev ruff check .`
2. `uv run --extra dev mypy`
3. `env -u all_proxy -u http_proxy -u https_proxy uv run --extra dev pytest -q`
4. `./scripts/release_gates.sh` when API/runtime paths are touched

## Rollback Strategy

1. Keep each migration change in isolated commits/PRs.
2. Use squash merge per migration slice.
3. If regression appears, revert one PR (single rollback unit), not partial file rollback.
