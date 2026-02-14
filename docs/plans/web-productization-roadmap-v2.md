# Resume Agent Web Productization Roadmap v2

Execution checklist: `docs/plans/web-productization-implementation-checklist.md`
Phase 1 acceptance: `docs/plans/web-phase1-acceptance.md`

## 1) Product Goal (90-day)

Build a web product that completes this user journey in one session:
upload resume -> provide target JD -> get gap analysis -> apply targeted rewrite -> preview -> export.

Success criteria:
- First meaningful output < 30s
- End-to-end completion rate >= 60%
- P95 request latency < 8s (excluding model timeout)
- Per-session cost visible and capped

## 2) Scope Boundaries

### In Scope (v1)
- Single-user web workspace per session
- Guided workflow (5 stages)
- JD matching and rewrite
- Human approval before write tools
- Resume preview + export

### Out of Scope (v1)
- Team collaboration
- Fine-grained RBAC
- Full template marketplace
- Advanced billing/checkout

## 3) Architecture Decisions

### Decision A: Keep Agent/Tool Core, add Web Adapter
- Reuse current `LLMAgent`, tools, session logic.
- Introduce `WorkspaceProvider` abstraction:
  - `LocalWorkspaceProvider` (CLI)
  - `RemoteWorkspaceProvider` (Web)

### Decision B: Python-first backend
- FastAPI + SSE for streaming.
- Reason: minimal integration cost with current Python async loop and tool system.

### Decision C: Provider strategy
- Internal provider routing only (user does not select provider in v1 UI).
- Server enforces provider/model policy and fallback rules.

## 4) Target System (v1)

```text
Web UI (Next.js or similar)
  -> FastAPI Gateway
      -> Session Service (state machine + persistence)
      -> Agent Runtime (LLMAgent + tools + approval gate)
      -> Workspace Service (remote files, preview artifacts)
      -> Storage (S3/GCS + DB + Redis optional)
      -> LLM Providers (Gemini / OpenAI-compatible)
```

## 5) Workflow State Machine

```text
draft -> resume_uploaded -> jd_provided -> gap_analyzed -> rewrite_applied -> exported
```

Allowed transitions:
- `draft -> resume_uploaded`
- `resume_uploaded -> jd_provided`
- `jd_provided -> gap_analyzed`
- `gap_analyzed -> rewrite_applied`
- `rewrite_applied -> exported`
- Any state can go to `cancelled`

Rules:
- Write tools require explicit approval unless auto-approve enabled per session.
- State updates are atomic and persisted with run_id.

## 6) API Contract (v1, minimal)

### Session
- `POST /api/v1/sessions` -> create session + workspace
- `GET /api/v1/sessions/{session_id}` -> session metadata + workflow state
- `POST /api/v1/sessions/{session_id}/resume` -> upload resume file
- `POST /api/v1/sessions/{session_id}/jd` -> submit JD text/link

### Chat/Run
- `POST /api/v1/sessions/{session_id}/messages` -> submit user message, returns `run_id`
- `GET /api/v1/sessions/{session_id}/runs/{run_id}/stream` -> SSE events
- `POST /api/v1/sessions/{session_id}/runs/{run_id}/interrupt` -> stop current run

### Approval
- `GET /api/v1/sessions/{session_id}/approvals` -> pending tool calls
- `POST /api/v1/sessions/{session_id}/approvals/{approval_id}/approve`
- `POST /api/v1/sessions/{session_id}/approvals/{approval_id}/reject`
- `POST /api/v1/sessions/{session_id}/settings/auto-approve` -> on/off

### Files/Export
- `GET /api/v1/sessions/{session_id}/files`
- `POST /api/v1/sessions/{session_id}/files/upload`
- `GET /api/v1/sessions/{session_id}/files/{path}`
- `POST /api/v1/sessions/{session_id}/export` -> generate export artifact

## 7) SSE Event Schema (stable contract)

Core event types:
- `run_started`
- `assistant_delta`
- `tool_call_proposed`
- `tool_call_approved`
- `tool_call_rejected`
- `tool_result`
- `run_interrupted`
- `run_completed`
- `run_failed`

Required envelope:
```json
{
  "event_id": "evt_xxx",
  "run_id": "run_xxx",
  "session_id": "sess_xxx",
  "type": "assistant_delta",
  "ts": "2026-02-14T12:00:00Z",
  "payload": {}
}
```

## 8) Delivery Plan

### Phase 1 (Weeks 1-2): Headless API MVP
Deliver:
- FastAPI service
- Session + message + SSE + approval APIs
- Remote workspace adapter (local disk implementation first)
- Existing CLI tests adapted for API integration

Exit criteria:
- curl-based end-to-end flow works (read/write + approval + interrupt)

### Phase 2 (Weeks 3-5): Minimal Web UI
Deliver:
- Chat panel + file panel + live preview
- Guided workflow sidebar (5 states)
- Approval modal
- Session resume after refresh

Exit criteria:
- Real user can finish one full resume tailoring flow without CLI

### Phase 3 (Weeks 6-8): Production Hardening
Deliver:
- Auth + tenant isolation
- Rate limiting + quota + timeout policies
- Object storage + TTL cleanup jobs
- Cost/usage metrics dashboard

Exit criteria:
- Stable under target concurrency with visible cost guardrails

## 9) Cost, Safety, and Reliability Guardrails

- Default max tool loop steps and repeated-call guard enabled.
- Per-session token/cost cap with graceful stop message.
- Hard timeout per run (server-side interrupt).
- File size/type validation at upload boundary.
- Audit log for write approvals and file mutations.

## 10) Testing Strategy

### Automated
- Contract tests for provider normalization (Gemini vs OpenAI-compatible).
- API integration tests for approval flow and interruption.
- SSE ordering tests (tool proposal -> approval -> execution).

### Manual
- Upload PDF/DOCX, generate rewrite, approve writes, export.
- Simulate provider errors (temperature constraints, timeout).
- Resume from previous session and continue rewrite.

## 11) Risks and Mitigations

- Provider-specific API drift:
  - Mitigation: adapter-layer retries + normalization tests + feature flags.
- Runaway tool loops:
  - Mitigation: loop guards + hard run timeout + cost cap.
- Storage growth:
  - Mitigation: workspace TTL + export retention policy.
- UX confusion around approvals:
  - Mitigation: explicit pending state + one-click approve/reject + auto-approve toggle.

## 12) Open Questions

- Final frontend stack choice (Next.js recommended for velocity)?
- Initial auth mode (single-tenant token vs full OAuth)?
- Export formats for v1 (PDF required now, or HTML/MD first)?
- Should provider fallback be automatic or opt-in per workspace?
