# packages/contracts

Phase 1 (Slice A) scaffold for shared API/session contracts in the target monorepo layout.

Current compatibility policy:

1. Runtime continues to import from `resume_agent/contracts/*`.
2. This folder mirrors contract modules for phased extraction.
3. Follow-up slices can switch adapters to import directly from this package path.
