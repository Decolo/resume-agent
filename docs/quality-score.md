# Quality Score

This document tracks quality trends over time using stable, low-noise metrics.

## Baseline (2026-02-16)

| Metric | Value | Source |
|---|---:|---|
| Python LOC (app + tests) | 16,370 | `wc -l` over `resume_agent/**/*.py` + `tests/**/*.py` |
| Largest module | `resume_agent/cli.py` (1,221 LOC) | size scan |
| Test suite status | 234 passed | `uv run --extra dev pytest -q` |
| Required CI checks | `test`, `lint`, `typecheck` | `.github/workflows/ci.yml` |
| Architecture boundary test | enabled | `tests/test_architecture_boundaries.py` |

## Scoring Model (v1)

Start at 100. Apply penalties:

1. CI red on default branch: -25
2. Required check missing: -15 each
3. Largest module > 1,500 LOC: -10
4. Largest module > 2,000 LOC: -20
5. Boundary test disabled/failing: -20
6. Open blocker bug without owner > 7 days: -5 each

## Current Score (v1)

- Score: **95/100**
- Notes:
  - No CI failures observed in current baseline.
  - Largest module (`cli.py`) is high but below 1,500 LOC threshold.
  - Staging cost guardrail validation is still pending.

## Update Cadence

Update this file:

1. Weekly during active development
2. Before each release candidate
3. After major architecture/tooling changes

## Next Improvement Targets

1. Reduce `resume_agent/cli.py` below 1,000 LOC.
2. Add load/perf metric tracking once Week 8 ops work starts.
3. Add trend history section (weekly snapshots).
