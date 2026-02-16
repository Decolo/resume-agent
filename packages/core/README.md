# packages/core

Core runtime/orchestration package.

Ownership:

1. Runtime code lives in `packages/core/resume_agent_core/*`.
2. Core modules must not depend on `apps/*`.
3. Legacy `resume_agent/*` compatibility wrappers have been retired.
