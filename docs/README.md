# Resume Agent Documentation

Maintainer-focused index for day-to-day development and operations.

If you want guided onboarding and background reading, use
**[Learning Index](./README.learn.md)**.

## Start Here

- **[Environment Setup](./setup/environment-setup.md)** - Config priority and provider setup
- **[Architecture Map](./architecture.md)** - Layering and dependency direction
- **[Execution Data Flow](./architecture/execution-data-flow.md)** - Runtime path from CLI to provider/tools
- **[Phase 1 Quick Reference](./api-reference/phase1-quick-reference.md)** - Runtime reliability APIs
- **[Session Persistence](./sessions/session-persistence.md)** - Session storage and restore flows

## Architecture

- **[ADR Index](./architecture/decisions/README.md)** - Decision records
- **[Phase 1 Improvements](./architecture/phase1-improvements.md)** - Reliability/perf/security details

## Ops and Maintenance

- **[Branch Protection Baseline](./ops/branch-protection.md)** - Required checks and merge policy
- **[Recurring Cleanup Workflow](./maintenance/recurring-cleanup.md)** - Periodic hygiene tasks
- **[Quality Score](./quality-score.md)** - Current quality snapshot and thresholds

## Usage Docs

- **[Export History](./usage/export-history.md)** - Export conversation history
- **[Export Verbose Example](./usage/export-verbose-example.md)** - Example output format

## Doc Hygiene Rules

- Keep this index aligned with files that actually exist.
- Keep maintainers' guidance in this file; move long-form tutorials to `README.learn.md`.
- Prefer linking to one authoritative doc over duplicating content.
