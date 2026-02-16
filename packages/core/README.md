# packages/core

Phase 2 (Slice C) scaffold for runtime orchestration and session core in the target monorepo layout.

Current compatibility policy:

1. Runtime may still import from `resume_agent/*`.
2. `resume_agent/{agent,agent_factory,llm,session,retry,observability,cache,preview}.py` are compatibility shims that forward to this package.
3. Follow-up slices can switch runtime imports to `packages/core/resume_agent_core/*` directly.
