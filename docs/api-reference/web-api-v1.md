# Web API v1 Contract (Headless Phase)

This document defines the backend HTTP contract for Phase 1 web productization.
It is intentionally minimal and decision-complete for implementation.

## Base

- Base path: `/api/v1`
- Content type: `application/json` unless noted
- Time format: ISO 8601 UTC (`2026-02-14T21:00:00Z`)
- IDs are opaque strings (`sess_*`, `run_*`, `appr_*`, `evt_*`)

## Common Error Shape

```json
{
  "error": {
    "code": "INVALID_STATE",
    "message": "Run is already completed",
    "details": {}
  }
}
```

## Error Codes

- `400` bad request (schema/validation)
- `404` resource not found
- `409` state conflict / already processed
- `422` policy violation (file/path constraints)
- `429` throttled / quota exceeded
- `500` internal error
- `502` provider upstream error
- `503` provider unavailable / timeout

---

## Session APIs

### `POST /sessions`

Create a new session and workspace.

Request:
```json
{
  "workspace_name": "my-resume",
  "auto_approve": false
}
```

Response `201`:
```json
{
  "session_id": "sess_01HXYZ",
  "created_at": "2026-02-14T21:00:00Z",
  "workflow_state": "draft",
  "settings": {
    "auto_approve": false
  }
}
```

### `GET /sessions/{session_id}`

Response `200`:
```json
{
  "session_id": "sess_01HXYZ",
  "workflow_state": "jd_provided",
  "active_run_id": "run_01HAAA",
  "pending_approvals_count": 1,
  "settings": {
    "auto_approve": false
  }
}
```

---

## File APIs

### `POST /sessions/{session_id}/files/upload`

Multipart form upload (`file` field).

Response `201`:
```json
{
  "file_id": "file_01",
  "path": "frontend-resume-improved-2026-02-03.md",
  "size": 8123,
  "mime_type": "text/markdown"
}
```

### `GET /sessions/{session_id}/files`

Response `200`:
```json
{
  "files": [
    {
      "path": "frontend-resume-improved-2026-02-03.md",
      "size": 8123,
      "updated_at": "2026-02-14T21:00:00Z"
    }
  ]
}
```

### `GET /sessions/{session_id}/files/{path}`

- For text files: response body text
- For binary artifacts: streamed download

---

## Run / Message APIs

### `POST /sessions/{session_id}/messages`

Start an asynchronous run.

Request:
```json
{
  "message": "Update resume summary for frontend role",
  "idempotency_key": "msg_001_optional"
}
```

Response `202`:
```json
{
  "run_id": "run_01HAAA",
  "status": "queued"
}
```

Idempotency:
- same `idempotency_key` + same session returns existing run
- different payload with same key returns `409`

### `GET /sessions/{session_id}/runs/{run_id}`

Response `200`:
```json
{
  "run_id": "run_01HAAA",
  "status": "waiting_approval",
  "started_at": "2026-02-14T21:01:00Z",
  "ended_at": null,
  "error": null
}
```

### `GET /sessions/{session_id}/runs/{run_id}/stream`

Server-Sent Events stream. Event contract is defined in
`docs/api-reference/sse-events-v1.md`.

### `POST /sessions/{session_id}/runs/{run_id}/interrupt`

Best-effort cancellation for active run.

Response `202`:
```json
{
  "run_id": "run_01HAAA",
  "status": "interrupting"
}
```

If already terminal (`completed|failed|interrupted`), return `200` with current status.

---

## Approval APIs

### `GET /sessions/{session_id}/approvals`

Response `200`:
```json
{
  "items": [
    {
      "approval_id": "appr_01",
      "run_id": "run_01HAAA",
      "tool_name": "file_write",
      "args": {
        "path": "frontend-resume-improved-2026-02-14.md"
      },
      "created_at": "2026-02-14T21:02:00Z",
      "status": "pending"
    }
  ]
}
```

### `POST /sessions/{session_id}/approvals/{approval_id}/approve`

Request:
```json
{
  "apply_to_future": false
}
```

Response `200`:
```json
{
  "approval_id": "appr_01",
  "run_id": "run_01HAAA",
  "status": "approved"
}
```

Semantics:
- approval continues the **same run**
- if `apply_to_future=true`, session setting `auto_approve=true`

### `POST /sessions/{session_id}/approvals/{approval_id}/reject`

Response `200`:
```json
{
  "approval_id": "appr_01",
  "run_id": "run_01HAAA",
  "status": "rejected"
}
```

### `POST /sessions/{session_id}/settings/auto-approve`

Request:
```json
{
  "enabled": true
}
```

Response `200`:
```json
{
  "enabled": true
}
```

---

## State Conflicts (`409`) Rules

- approving/rejecting an already processed approval -> `409`
- approving/rejecting an approval not belonging to active pending set -> `409`
- submitting message when session has an active non-terminal run -> `409`
