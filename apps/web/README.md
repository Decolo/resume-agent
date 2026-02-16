# apps/web

Phase 3 (Slice F) scaffold for static web UI asset ownership in the target monorepo layout.

Current compatibility policy:

1. Static UI source lives in `apps/web/ui`.
2. API runtime resolves `apps/web/ui` first and keeps `resume_agent/web/ui` as fallback during migration.
3. Compatibility fallback can be removed after one stable release cycle.
