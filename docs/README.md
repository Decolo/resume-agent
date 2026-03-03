# Resume Agent Documentation

Maintainer-focused index for day-to-day development and operations.

If you want guided onboarding and background reading, use
**[Learning Index](./README.learn.md)**.

## Start Here

- **[Environment Setup](./setup/environment-setup.md)** - Config priority and provider setup
- **[Documentation Standards](./standards/documentation-organization.md)** - Stable doc structure and naming rules
- **[Architecture Map](./architecture.md)** - Layering and dependency direction
- **[Execution Data Flow](./architecture/execution-data-flow.md)** - Runtime path from CLI to provider/tools
- **[Phase 1 Quick Reference](./api-reference/phase1-quick-reference.md)** - Runtime reliability APIs
- **[LinkedIn Tools Reference](./api-reference/linkedin-tools.md)** - `job_search` and `job_detail` contracts and policy
- **[Session Persistence](./sessions/session-persistence.md)** - Session storage and restore flows

## Architecture

- **[ADR Index](./architecture/adrs/README.md)** - Decision records
- **[Kimi CLI History Design Reference](./learn/kimi-cli-history-design-reference.md)** - External session/compaction design learnings
- **[PI-Mono History Design Reference](./learn/pi-mono-history-design-reference.md)** - External history-management design learnings
- **[Phase 1 Improvements (Archived)](./archive/phase1-improvements.md)** - Historical reliability/perf/security details

## Ops and Maintenance

- **[Branch Protection Baseline](./ops/branch-protection.md)** - Required checks and merge policy
- **[Recurring Cleanup Workflow](./maintenance/recurring-cleanup.md)** - Periodic hygiene tasks
- **[Quality Scorecard](./ops/quality-scorecard.md)** - Current quality snapshot and thresholds
- **[History Management Roadmap](./todo/history-management-roadmap.md)** - Planned compaction and branchable-history work

## Usage Docs

- **[Export History](./usage/export-history.md)** - Export conversation history
- **[Export Verbose Example](./usage/export-verbose-example.md)** - Example output format

## Doc Hygiene Rules

- Keep this index aligned with files that actually exist.
- Keep maintainers' guidance in this file; move long-form tutorials to `README.learn.md`.
- Prefer linking to one authoritative doc over duplicating content.
- Follow `docs/standards/documentation-organization.md` for naming, placement, and archive lifecycle.
