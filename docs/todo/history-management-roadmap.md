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

- [ ] Hard-remove built-in multi-agent subagents to simplify architecture
  - Remove `AutoAgent`, `IntentRouter`, `OrchestratorAgent`, and specialized
    subagent runtime paths.
  - Remove multi-agent config surface (`multi_agent.*`, `routing.*`) and CLI
    force flags tied to multi-agent mode.
  - Remove delegation-related session serialization fields and dead code paths.
  - Archive superseded architecture/docs and keep one concise single-agent
    architecture source of truth.
  - Define migration notes for existing users who rely on multi-agent settings.

- [ ] Harden tool-call argument integrity for write operations
  - Prevent stream/tool-call argument degradation from producing `{}` at
    execution time (especially `file_write(path, content)`).
  - Add end-to-end regression coverage for large save workflows (e.g. saving
    20+ job posts) in interactive approval mode.
  - Add resilient fallback strategy when a write tool call arrives with missing
    required args (auto-repair prompt or regrouped single-call batch write).
  - Track and reduce approval-path write failure rate in session logs.
