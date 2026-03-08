# Agent Loop Approval Refactor (Archived)

Archived: 2026-03-09
Source TODO: `docs/todo/agent-loop-improvements.md`

## Completed Scope

### 1) Inline approval control flow stabilized

- Replaced pause-and-return flow with inline `Approval.request(...)` future-based gating.
- Approval request/response is piped through Wire (`ApprovalRequest` with action + description).
- When no UI subscriber exists and no approval handler is configured, loop fails fast with explicit error.

### 2) Session-level action-scoped approval

- `approve_all` now records approval by action key (for example `file_write`) instead of global blanket approval.
- Session-scoped action approvals persist across turns in `LLMAgent` state.
- Global yolo auto-approve remains a separate switch.

### 3) Approval metadata ownership moved to tool layer

- Introduced `ApprovalRequestSpec` in `BaseTool`.
- Tools can provide `build_approval_request(**kwargs)` for:
  - `action`: stable scope key for approval memory
  - `description`: user-facing context
- File mutation tools now provide richer approval context:
  - `FileWriteTool`: action `file_write`, diff preview in description
  - `FileEditTool`: action `file_edit`, diff preview in description
  - `FileRenameTool`: action `file_rename`, operation summary

### 4) Loop/tool boundary cleanup

- Removed loop-side hardcoded write approval request construction.
- `LLMAgent` now orchestrates approval generically per tool call.
- Approval preview generation is no longer coupled to loop-side file inspection.

## Validation

- Targeted tests and full suite passed at archive time.
- Full test snapshot: `348 passed, 2 skipped`.

## Follow-ups Not Included In This Archive

- Provider-specific malformed function-call resilience tuning remains separate work.
- Incident-specific write-sanity heuristics (if needed) should be tracked as independent TODO items.
