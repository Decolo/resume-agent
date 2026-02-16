# packages/providers

Phase 1 (Slice B) scaffold for provider adapters in the target monorepo layout.

Current compatibility policy:

1. Runtime keeps importing from `resume_agent/providers/*`.
2. `resume_agent/providers/*` modules are compatibility shims that forward to this package.
3. Follow-up slices can switch runtime imports to `packages/providers/resume_agent_providers/*` directly.
