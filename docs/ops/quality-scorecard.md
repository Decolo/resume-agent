# Quality Scorecard

This document tracks low-noise quality signals for the current single-package
runtime (`resume_agent/*`).

## Snapshot (2026-02-28)

| Metric | Value | Source |
|---|---:|---|
| Python LOC (`resume_agent` + `tests`) | 16,284 | `find resume_agent tests -name '*.py' -type f -print0 \| xargs -0 wc -l` |
| Largest module | `resume_agent/cli/app.py` (1,456 LOC) | `find resume_agent -name '*.py' ... \| sort -nr` |
| Architecture boundary tests | enabled | `tests/architecture/test_architecture_boundaries.py` |
| Required CI checks (target) | `test`, `lint`, `typecheck` | `.github/workflows/ci.yml` |

## Scoring Model (v1)

Start at 100. Apply penalties:

1. CI red on default branch: -25
2. Required check missing: -15 each
3. Largest module > 1,500 LOC: -10
4. Largest module > 2,000 LOC: -20
5. Boundary test disabled/failing: -20
6. Open blocker bug without owner > 7 days: -5 each

## Current Score (v1)

- Score: **100/100** (snapshot-based; does not include remote issue tracker state)
- Notes:
  - Largest module is close to threshold (1,456 / 1,500).
  - Keep refactor pressure on `resume_agent/cli/app.py`.

## Update Cadence

Update this file:

1. Weekly during active development
2. Before each release candidate
3. After major architecture/tooling changes

## Next Improvement Targets

1. Keep `resume_agent/cli/app.py` below 1,500 LOC.
2. Add trend snapshots (weekly table) after 4+ data points.
3. Keep boundary tests and CI checks mandatory on `main`.
