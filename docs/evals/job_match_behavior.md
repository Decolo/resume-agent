# Job Match Behavior Evaluation

This evaluates `job_match` as a black-box behavior contract, not internal implementation details.

## What It Validates

1. Scenario behavior by layer score:
- `skills`
- `yoe`
- `location`
- `company_experience`

2. Metamorphic robustness:
- paraphrased JD should not cause large score jumps
- unrelated resume noise should not cause large score jumps

3. Tool contract:
- `next_step` includes a deep-analysis hint

## Fixture Source

- [`tests/behavior/fixtures/job_match_cases.yaml`](/tmp/resume-agent-jobmatch-wt/tests/behavior/fixtures/job_match_cases.yaml)

The YAML defines:
1. baseline resume
2. black-box cases with expected min/max bounds
3. metamorphic checks (paraphrase/noise) with max deltas

## Run with Pytest

```bash
uv run pytest -q tests/behavior/test_job_match_behavior.py
```

## Run Offline Eval Script

Human-readable:

```bash
uv run python scripts/eval_job_match.py --strict
```

JSON output:

```bash
uv run python scripts/eval_job_match.py --strict --json
```

## Pass Criteria

1. All scenario bounds pass.
2. All metamorphic deltas are within configured thresholds.
3. Strict mode exits with code `0`.

## Notes

1. This suite is designed to catch behavior regressions from weight tuning and extraction logic changes.
2. Keep fixture thresholds stable and explicit; adjust only when product intent changes.
