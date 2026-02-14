# Web Productization Implementation Checklist

This checklist executes `web-productization-roadmap-v2.md` in a delivery-friendly sequence.

## Phase 1 (Weeks 1-2): Headless API MVP

## Week 1
- [x] Finalize API contract for session/message/approval/stream endpoints.
- [ ] Implement `WorkspaceProvider` interface and `RemoteWorkspaceProvider` (local-disk backend first).
- [ ] Add session lifecycle APIs (`create/get`) and file upload/list APIs.
- [x] Add run creation API (`POST /messages`) and run metadata model (`run_id`, status, timestamps).

## Week 2
- [x] Implement SSE stream endpoint with stable event envelope.
- [x] Wire approval APIs to existing pending tool-call gate.
- [x] Implement interrupt API mapped to runtime cancellation.
- [x] Add integration tests for: read->write approval->apply, reject path, interrupt path.
- [ ] Add basic observability fields to API logs (`session_id`, `run_id`, provider, model).

## Phase 2 (Weeks 3-5): Minimal Web UI

## Week 3
- [ ] Build chat panel + message timeline consuming SSE events.
- [ ] Build file panel (upload/list/open/download).
- [ ] Show pending approvals as explicit UI state.

## Week 4
- [ ] Build guided workflow sidebar (5 states).
- [ ] Add JD input UX (text/link) and stage transitions.
- [ ] Build approval modal (approve/reject/auto-approve toggle).

## Week 5
- [ ] Build preview pane and diff view for rewritten resume.
- [ ] Implement export UX and artifact download.
- [ ] Add refresh-safe session restore (resume active session state on reload).
- [ ] Run manual E2E acceptance flow and fix critical UX blockers.

## Phase 3 (Weeks 6-8): Production Hardening

## Week 6
- [ ] Add authentication and tenant scoping model.
- [ ] Add rate limit and per-session quota controls.
- [ ] Add strict upload constraints (size/type/path validation).

## Week 7
- [ ] Add object storage backend and lifecycle cleanup (TTL).
- [ ] Add cost telemetry (`tokens`, `estimated_cost`) per run/session.
- [ ] Add fallback and retry policy configuration for provider errors.

## Week 8
- [ ] Add dashboards/alerts for error rate, latency, cost, queue depth.
- [ ] Load test target concurrency and tune runtime limits.
- [ ] Finalize release checklist and rollback playbook.

## Module Checklist (Cross-cutting)

- **Agent Runtime**
  - [ ] Preserve existing tool-loop guard behavior in API mode.
  - [ ] Preserve write approval semantics exactly (pause before execution).
  - [ ] Ensure cancellation is idempotent and leaves session in consistent state.

- **Provider Compatibility**
  - [ ] Keep normalized request/response boundary in provider adapters.
  - [ ] Add contract tests for Gemini + OpenAI-compatible tool call formats.
  - [ ] Add regression tests for provider-specific constraints (temperature/thinking/etc.).

- **Session & Persistence**
  - [ ] Persist workflow stage and pending approvals per session.
  - [ ] Persist run events for debugging and replay.
  - [ ] Ensure backwards compatibility of session schema versions.

- **Security**
  - [ ] File path sandbox enforcement in remote workspace.
  - [ ] Audit log for approvals and file mutations.
  - [ ] Redaction policy for sensitive user content in logs.

## Release Gates

- [ ] API contract tests all pass.
- [ ] E2E happy path (upload -> jd -> rewrite -> approve -> export) passes.
- [ ] Interrupt and reject edge cases pass.
- [ ] Cost guardrails verified in staging.
- [ ] Documentation updated for setup, API, and operations.
