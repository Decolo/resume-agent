# History Management Roadmap

Created: 2026-03-01

This file tracks future work for conversation history management in
`resume-agent`.

## TODOs

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
