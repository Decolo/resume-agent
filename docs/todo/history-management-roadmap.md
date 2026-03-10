# History Management Roadmap

Created: 2026-03-01

This file tracks future work for conversation history management in
`resume-agent`.

## TODOs

- [ ] Add summary-based compaction for long conversations
  - Trigger before overflow using a threshold:
    `estimated_context_tokens + reserve_tokens >= model_context_window`.
  - Keep a recent raw-message tail (`tail_tokens`) to preserve short-term
    execution state.
  - Preserve tool call/response pair integrity across compaction boundaries.
  - Add one automatic retry path when provider reports context overflow.

- [ ] Evaluate and design tree-based history for branch/rewind workflows
  - Define entry schema (`entry_id`, `parent_id`, `entry_type`, timestamps).
  - Keep prompt materialization linear by active leaf path.
  - Ensure session persistence and migration from current linear history format.
  - Propose minimal CLI commands for branch navigation and inspection.

- [x] Simplify runtime to single-agent only
  - Removed built-in subagent runtime paths and related orchestration code.
  - Removed obsolete config surface and CLI mode toggles from the old architecture.
  - Simplified session serialization and architecture docs around one runtime path.

- [ ] Harden tool-call argument integrity for write operations
  - Prevent stream/tool-call argument degradation from producing `{}` at
    execution time (especially `file_write(path, content)`).
  - Add end-to-end regression coverage for large save workflows (e.g. saving
    20+ job posts) in interactive approval mode.
  - Add resilient fallback strategy when a write tool call arrives with missing
    required args (auto-repair prompt or regrouped single-call batch write).
  - Track and reduce approval-path write failure rate in session logs.

- [ ] Refactor session history UX into a unified `/resume` command
  - Replace fragmented `/sessions` + `/load <id>` flow with one `/resume`
    entrypoint that opens an interactive resume/session picker.
  - Show concise metadata in picker: session name, updated time, message count,
    token usage, and workspace.
  - Support actions in the same flow: load session, start new session, and
    optionally resume from latest.
  - Keep backward compatibility aliases during transition, then deprecate old
    commands with clear guidance.
