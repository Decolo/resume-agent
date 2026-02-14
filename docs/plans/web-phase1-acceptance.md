# Web Phase 1 Acceptance Scenarios

This file is the acceptance baseline for Phase 1 (headless API).

## A. Happy Path (Read -> Write Approval -> Continue)

Given:
- session exists
- auto-approve disabled

Steps:
1. `POST /sessions/{id}/messages` with edit request
2. stream receives `run_started`
3. stream receives `tool_call_proposed`
4. `POST /approvals/{approval_id}/approve`
5. stream receives `tool_call_approved`
6. stream receives `tool_result`
7. stream receives `run_completed`

Expected:
- same `run_id` throughout
- file mutation occurs only after approval

## B. Reject Path

Steps:
1. start run that proposes write tool
2. `POST /approvals/{approval_id}/reject`
3. stream receives `tool_call_rejected`
4. run ends (`run_completed` with rejection reason)

Expected:
- target file unchanged
- no write tool execution after rejection

## C. Interrupt Path

Steps:
1. start long-running run
2. `POST /runs/{run_id}/interrupt`
3. stream eventually receives `run_interrupted`

Expected:
- run status becomes `interrupted`
- no further non-tail business events after terminal interrupt

## D. Idempotency / Conflict

Scenarios:
- approve same `approval_id` twice -> second call returns `409`
- reject processed `approval_id` -> `409`
- interrupt terminal run -> `200` with current terminal status
- same `idempotency_key` + same payload on `/messages` -> returns existing `run_id`

## E. Event Ordering

Validate:
- envelope fields always present
- monotonic `event_id` within run
- exactly one terminal event
- run status endpoint and stream terminal event match

## F. Provider Error Surface

Simulate provider errors and confirm:
- terminal event is `run_failed`
- `GET /runs/{id}` shows `failed` with error metadata
- API returns standardized error shape

## Exit Criteria

- All scenarios above pass in CI integration suite.
- No state divergence between:
  - run status endpoint
  - approval endpoint
  - streamed event history
