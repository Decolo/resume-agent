# Web Productization Implementation Checklist

This checklist executes `web-productization-roadmap-v2.md` in a delivery-friendly sequence.

## Phase 1 (Weeks 1-2): Headless API MVP

## Week 1
- [x] Finalize API contract for session/message/approval/stream endpoints.
- [x] Implement `WorkspaceProvider` interface and `RemoteWorkspaceProvider` (local-disk backend first).
- [x] Add session lifecycle APIs (`create/get`) and file upload/list APIs.
- [x] Add run creation API (`POST /messages`) and run metadata model (`run_id`, status, timestamps).

## Week 2
- [x] Implement SSE stream endpoint with stable event envelope.
- [x] Wire approval APIs to existing pending tool-call gate.
- [x] Implement interrupt API mapped to runtime cancellation.
- [x] Add integration tests for: read->write approval->apply, reject path, interrupt path.
- [x] Add basic observability fields to API logs (`session_id`, `run_id`, provider, model).

## Phase 2 (Weeks 3-5): Minimal Web UI

## Week 3
- [x] Build chat panel + message timeline consuming SSE events.
- [x] Build file panel (upload/list/open/download).
- [x] Show pending approvals as explicit UI state.

## Week 4
- [x] Build guided workflow sidebar (5 states).
- [x] Add JD input UX (text/link) and stage transitions.
- [x] Build approval modal (approve/reject/auto-approve toggle).

## Week 5
- [x] Build preview pane and diff view for rewritten resume.
- [x] Implement export UX and artifact download.
- [x] Add refresh-safe session restore (resume active session state on reload).
- [ ] Run manual E2E acceptance flow and fix critical UX blockers.

## Phase 3 (Weeks 6-8): Production Hardening

## Week 6
- [x] Add authentication and tenant scoping model.
- [x] Add rate limit and per-session quota controls.
- [x] Add strict upload constraints (size/type/path validation).

## Week 7
- [x] Add object storage backend and lifecycle cleanup (TTL).
- [x] Add cost telemetry (`tokens`, `estimated_cost`) per run/session.
- [x] Add fallback and retry policy configuration for provider errors.

## Week 8
- [x] Add dashboards/alerts for error rate, latency, cost, queue depth.
- [x] Load test target concurrency and tune runtime limits.
- [x] Finalize release checklist and rollback playbook.

## Module Checklist (Cross-cutting)

- **Agent Runtime**
  - [x] Preserve existing tool-loop guard behavior in API mode.
  - [x] Preserve write approval semantics exactly (pause before execution).
  - [x] Ensure cancellation is idempotent and leaves session in consistent state.

- **Provider Compatibility**
  - [x] Keep normalized request/response boundary in provider adapters.
  - [x] Add contract tests for Gemini + OpenAI-compatible tool call formats.
  - [x] Add regression tests for provider-specific constraints (temperature/thinking/etc.).

- **Session & Persistence**
  - [x] Persist workflow stage and pending approvals per session.
  - [x] Persist run events for debugging and replay.
  - [x] Ensure backwards compatibility of session schema versions.

- **Security**
  - [x] File path sandbox enforcement in remote workspace.
  - [x] Audit log for approvals and file mutations.
  - [x] Redaction policy for sensitive user content in logs.

## Release Gates

- [x] API contract tests all pass.
- [x] E2E happy path (upload -> jd -> rewrite -> approve -> export) passes.
- [x] Interrupt and reject edge cases pass.
- [ ] Cost guardrails verified in staging.
- [x] Documentation updated for setup, API, and operations.
