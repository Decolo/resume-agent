# SSE Event Contract v1

This document defines the server-sent event schema for run streaming.

## Transport

- Endpoint: `GET /api/v1/sessions/{session_id}/runs/{run_id}/stream`
- Protocol: SSE (`text/event-stream`)
- Retry strategy: client reconnect with last processed `event_id`

## Event Envelope (required)

```json
{
  "event_id": "evt_01HBBB",
  "session_id": "sess_01HXYZ",
  "run_id": "run_01HAAA",
  "type": "assistant_delta",
  "ts": "2026-02-14T21:03:00Z",
  "payload": {}
}
```

Field rules:
- `event_id`: monotonic within a run
- `session_id`/`run_id`: immutable for stream lifetime
- `type`: one of defined event types below
- `payload`: type-specific object

## Event Types

### `run_started`

Payload:
```json
{
  "status": "running"
}
```

### `assistant_delta`

Incremental assistant text output.

Payload:
```json
{
  "text": "I can help you rewrite your summary..."
}
```

### `tool_call_proposed`

A write tool call requires approval.

Payload:
```json
{
  "approval_id": "appr_01",
  "tool_name": "file_write",
  "args": {
    "path": "frontend-resume-improved-2026-02-14.md"
  }
}
```

### `tool_call_approved`

Payload:
```json
{
  "approval_id": "appr_01"
}
```

### `tool_call_rejected`

Payload:
```json
{
  "approval_id": "appr_01",
  "reason": "user_rejected"
}
```

### `tool_result`

Payload:
```json
{
  "tool_name": "file_write",
  "success": true,
  "result": "Successfully wrote 1523 characters to frontend-resume-improved-2026-02-14.md"
}
```

### `run_interrupted`

Payload:
```json
{
  "status": "interrupted"
}
```

### `run_completed`

Payload:
```json
{
  "status": "completed",
  "final_text": "Done. I created frontend-resume-improved-2026-02-14.md"
}
```

### `run_failed`

Payload:
```json
{
  "status": "failed",
  "error_code": "PROVIDER_ERROR",
  "message": "LLM request failed"
}
```

## Ordering and Delivery Guarantees

- Events are emitted in run execution order.
- `run_started` is first event.
- Exactly one terminal event is expected:
  - `run_completed` or `run_failed` or `run_interrupted`
- Best-effort interrupt: small tail events may appear before terminal interrupt event.

## Reconnect Behavior

- Client should track last received `event_id`.
- On reconnect, server may replay events after `event_id`.
- If replay is unavailable, client should fetch run status via `GET /runs/{run_id}`.
