# Run and Approval State Machine (v1)

This state machine defines the runtime lifecycle for web/API execution.

## Run State Machine

```text
queued -> running -> waiting_approval -> running -> completed
                               |                |
                               |                -> failed
                               |
                               -> rejected -> completed

running -> interrupting -> interrupted
waiting_approval -> interrupting -> interrupted
```

Terminal run states:
- `completed`
- `failed`
- `interrupted`

## Approval State Machine

```text
pending -> approved
pending -> rejected
```

Terminal approval states:
- `approved`
- `rejected`

## Transition Rules

### Run creation
- `POST /messages` creates run in `queued`
- scheduler/executor moves `queued -> running`

### Waiting for approval
- while `running`, if model emits write tool call and `auto_approve=false`:
  - runtime does not execute write tool
  - creates approval record(s) in `pending`
  - run transitions to `waiting_approval`

### Approve
- `POST /approvals/{id}/approve`:
  - approval `pending -> approved`
  - execute pending tool call(s)
  - run continues in **same run_id** (`waiting_approval -> running`)

### Reject
- `POST /approvals/{id}/reject`:
  - approval `pending -> rejected`
  - run ends without applying tool call changes
  - default terminal state: `completed` with rejection reason

### Interrupt
- `POST /runs/{id}/interrupt`:
  - best-effort cancellation
  - `running|waiting_approval -> interrupting -> interrupted`
  - tail events may still arrive during cancellation window

## Invariants

- One session can have at most one active run (`queued|running|waiting_approval|interrupting`)
- Approval belongs to exactly one `session_id + run_id`
- Approval can be consumed exactly once
- All events emitted by a run carry stable `session_id` and `run_id`

## Mapping to Existing Runtime

Current behavior in `resume_agent/llm.py` already supports:
- pending write tool call pause (`_pending_tool_calls`)
- explicit approve/reject actions (`approve_pending_tool_calls`, `reject_pending_tool_calls`)
- cancellation propagation (`asyncio.CancelledError`)

Web runtime should wrap these behaviors with explicit run state persistence and SSE emission.
