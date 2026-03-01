# Resume Agent Learning Index

Learning-focused documentation map for onboarding, background context, and
deep dives.

For day-to-day maintenance docs, use **[Maintainer Index](./README.md)**.

## Suggested Reading Order

1. **[Environment Setup](./setup/environment-setup.md)** - Configure local runtime first.
2. **[Architecture Map](./architecture.md)** - Understand layers and dependency rules.
3. **[Session Persistence](./sessions/session-persistence.md)** - Learn how runtime state is stored.
4. **[Phase 1 Quick Reference](./api-reference/phase1-quick-reference.md)** - See reliability APIs in code form.
5. **[Phase 1 Improvements (Archived)](./archive/phase1-improvements.md)** - Read historical implementation rationale and outcomes.

## Core Reference

- **[Documentation Standards](./standards/documentation-organization.md)** - How docs are organized and maintained.
- **[Architecture Decision Records](./architecture/adrs/README.md)** - Why major choices were made.
- **[Quality Scorecard](./ops/quality-scorecard.md)** - How project health is tracked.
- **[Branch Protection Baseline](./ops/branch-protection.md)** - CI and merge guardrails.

## Runtime and UX Details

- **[Export History](./usage/export-history.md)** - Export command behavior.
- **[Export Verbose Example](./usage/export-verbose-example.md)** - Concrete export output.

## Deep Dives

- **[Event Loop & Async Patterns](./learn/event-loop-async-patterns.md)** - Async mental model used by the CLI.
- **[Kimi CLI History Design Reference](./learn/kimi-cli-history-design-reference.md)** - Session-scoped history and compaction design learnings.
- **[PI-Mono History Design Reference](./learn/pi-mono-history-design-reference.md)** - Tree history, compaction, and branch context learnings.
- **[Vercel AI SDK Streaming Notes](./learn/vercel-ai-sdk-streaming.md)** - External streaming architecture analysis.
- **[LinkedIn Browser PoC](./research/linkedin-browser-poc.md)** - Experimental browser automation notes.

## Keeping This Useful

- Prefer additive context: rationale, gotchas, and non-obvious constraints.
- Avoid restating obvious README content or file-tree summaries.
- Remove entries when the underlying docs are deleted or superseded.
