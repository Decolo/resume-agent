# Resume Agent Documentation

This index organizes the docs by task so you can find things quickly.

## Start Here
- **[Environment Setup](./setup/environment-setup.md)** - Configure API keys and local config
- **[Session Persistence](./sessions/session-persistence.md)** - Save and restore sessions
- **[Export History](./usage/export-history.md)** - Save or copy conversation history

## Structure

### Setup
- **[Environment Setup](./setup/environment-setup.md)** - API keys and config priority

### Usage
- **[Export History](./usage/export-history.md)** - Export conversation history
- **[Export Verbose Example](./usage/export-verbose-example.md)** - Sample verbose export output

### Sessions
- **[Session Persistence](./sessions/session-persistence.md)** - Save/load sessions and architecture

### Reference
- **[API Reference](./api-reference/phase1-quick-reference.md)** - Code examples and API usage
- **[Web API v1 Contract](./api-reference/web-api-v1.md)** - Headless web backend API contract
- **[SSE Event Contract v1](./api-reference/sse-events-v1.md)** - Streaming event schema
- **[Architecture Map](./architecture.md)** - High-level module/dependency map
- **[Quality Score](./quality-score.md)** - Baseline quality metrics and trend tracking

### Architecture
- **[Phase 1 Improvements](./architecture/phase1-improvements.md)** - Technical improvements
- **[Run State Machine v1](./architecture/run-state-machine.md)** - Run/approval lifecycle and transitions

### Learn
- **[Event Loop & Async Patterns](./learn/event-loop-async-patterns.md)** - Async concepts and patterns

### Research
- (Archived) Vercel AI SDK analysis moved to `./archive/research/`

### Product
- **[Productization Checklist](./product/productization-checklist.md)** - Product readiness notes

### Ops
- **[Release Gates and Rollback Playbook](./ops/release-gates.md)** - Release readiness checks and rollback steps
- **[Branch Protection Baseline](./ops/branch-protection.md)** - Required checks and PR workflow baseline

### Plans
- **[Web Productization Roadmap v2](./plans/web-productization-roadmap-v2.md)** - Active execution roadmap
- **[Web Productization Implementation Checklist](./plans/web-productization-implementation-checklist.md)** - Week-by-week and module checklist
- **[Web Phase 1 Acceptance](./plans/web-phase1-acceptance.md)** - Integration acceptance scenarios
- **[Product Direction Ideas](./plans/product-direction-ideas.md)** - Active exploration notes
- **[Active Plan Folder](./plans/active/README.md)** - Where in-progress plans should live
- **[Completed Plan Folder](./plans/completed/README.md)** - Where finished plans should move

### Archive
- **[Archive Index](./archive/README.md)** - Completed or outdated docs retained for reference

## Doc Lifecycle Rules

- Keep only authoritative, currently-used guides in active folders.
- Move completed design docs and one-off implementation notes into `docs/archive/`.
- Keep troubleshooting content in archive unless it reflects current behavior and is actively maintained.

## CLI Commands (Quick View)

| Command | Description |
|---------|-------------|
| `/help` | Show available commands and example prompts |
| `/reset` | Clear conversation history |
| `/save [name]` | Save current session (optional custom name) |
| `/load [number]` | Load a saved session (shows picker if no number) |
| `/sessions` | List all saved sessions with numbers |
| `/delete-session <number>` | Delete a saved session by number |
| `/files` | List all files in workspace |
| `/config` | Show current configuration |
| `/export [target] [format]` | Export conversation history |
| `/approve` | Approve pending tool call(s) |
| `/reject` | Reject pending tool call(s) |
| `/pending` | List pending tool approvals |
| `/auto-approve [on|off|status]` | Control auto-approval for write tools |
| `/agents` | Show agent statistics (multi-agent mode) |
| `/trace` | Show delegation trace (multi-agent mode) |
| `/delegation-tree` | Show delegation stats (multi-agent mode) |
| `/quit` or `/exit` | Exit the agent |

## Next Steps

1. **Configure the environment**: [Environment Setup](./setup/environment-setup.md)
2. **Run the agent** and try a small task
3. **Enable session workflow**: [Session Persistence](./sessions/session-persistence.md)
4. **Export when needed**: [Export History](./usage/export-history.md)

If you need deeper details, jump to the appropriate section above.
