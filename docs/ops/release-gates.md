# Release Gates and Rollback Playbook

This guide defines the release gates for web productization and how to roll back safely.

## Automated Release Gates

Run:

```bash
./scripts/release_gates.sh
```

This script enforces:

1. API contract tests pass (`tests/test_web_api_week1.py`)
2. Happy path pass (`upload -> jd -> rewrite -> approve -> export` via integration tests)
3. Interrupt/reject edge cases pass

## Gate-to-Test Mapping

| Gate | Evidence |
|------|----------|
| API contract tests all pass | `tests/test_web_api_week1.py` |
| E2E happy path passes | `test_resume_and_jd_workflow_transitions`, `test_export_endpoint_creates_artifact_and_marks_exported` |
| Interrupt/reject edge cases pass | `test_reject_flow_completes_without_tool_result`, `test_interrupt_flow_returns_interrupted_terminal_event`, `test_interrupt_terminal_run_returns_200_with_current_status` |

## Manual Staging Gate: Cost Guardrails

Automated unit/integration tests validate telemetry fields and usage aggregation, but cost guardrails still require staging verification.

Checklist:

1. Deploy candidate to staging with production-like provider settings.
2. Run a representative flow (at least 10 sessions).
3. Confirm per-run and per-session usage/cost telemetry is emitted.
4. Confirm budget/cap behavior (if configured) triggers graceful stop messaging.
5. Record validation notes in release PR.

Keep `Cost guardrails verified in staging` unchecked until this is done.

## Manual E2E Acceptance (UI)

Use this before release candidates:

1. Create a new session in web UI.
2. Upload resume file.
3. Submit JD text or URL.
4. Run rewrite request.
5. Approve pending write call.
6. Confirm file mutation and preview update.
7. Export artifact and download it.
8. Reload page and verify session restore.

If any step fails, open a blocker issue and do not mark acceptance complete.

## Rollback Playbook (v1)

Use this flow when production errors/regressions exceed thresholds.

1. Stop rollout:
   - Disable new deploy traffic (or freeze rollout in platform controls).
2. Identify previous known-good revision:
   - Select last successful release tag/commit with passing release gates.
3. Roll back backend first:
   - Deploy previous API/backend revision.
   - Verify `/healthz` and core session endpoints.
4. Roll back frontend next (if needed):
   - Redeploy last known-good UI artifact.
5. Verify critical journey:
   - Create session -> upload -> jd -> rewrite -> approve -> export.
6. Communicate status:
   - Post incident update with rollback revision and customer impact.
7. Open follow-up:
   - Create remediation issue with root cause + permanent fix plan.

## Notes

- Keep this document in sync with `docs/plans/web-productization-implementation-checklist.md`.
- Do not mark release gates complete without test output or staging evidence in PR notes.
