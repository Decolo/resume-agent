# Branch Protection Baseline

This document defines the minimum branch protection and PR workflow for this repository.

## Target Branch

- Protected branch: `main`
- Default working branch for development: `dev` (or short-lived topic branches from `dev`)

## Required Status Checks

Configure GitHub branch protection to require these checks on `main`:

1. `test (py3.11)`
2. `lint (ruff)`
3. `typecheck (mypy)`

Keep `Require branches to be up to date before merging` enabled.

## Merge Policy

1. Direct pushes to `main`: avoid by default.
2. Use PRs for all behavior/config changes.
3. Keep PRs small and scoped to one concern.
4. Squash merge is recommended for clean history.

## Developer Workflow

1. Work on `dev` or `feat/<topic>` branch.
2. Run local checks:
   - `uv run --extra dev ruff check .`
   - `uv run --extra dev mypy`
   - `env -u all_proxy -u http_proxy -u https_proxy uv run --extra dev pytest -q`
3. Push branch and open PR to `main`.
4. Merge only after required checks are green.

## Why This Baseline

- Keeps CI guarantees stable over time.
- Reduces risk from large or agent-generated patches.
- Ensures each change has explicit review and rollback unit.
