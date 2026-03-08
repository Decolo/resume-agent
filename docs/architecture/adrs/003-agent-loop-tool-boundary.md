# ADR-003: Agent Loop and Tool Responsibility Boundary

- Status: Accepted
- Date: 2026-03-08

## Context

`LLMAgent` is the runtime control loop and `resume_agent/tools/*` are adapters for side effects.
Over time, file-mutation UX logic (for example write diff preview for approval) moved into the loop layer.
That created two problems:

1. Architectural coupling: loop code started reading files directly.
2. Scaling risk: each new mutation tool could require loop-specific branching.

We need a stable rule for where mutation semantics and approval preview logic should live.

## Decision

1. `LLMAgent` remains orchestration-only:
   - provider request/parse/retry
   - step lifecycle and history updates
   - approval flow orchestration
   - tool dispatch and observability
2. Tool layer owns mutation semantics and side effects:
   - I/O and resource mutation
   - idempotency/no-op logic
   - operation-specific validation
   - approval preview details via `build_approval_context(**kwargs)`
3. `LLMAgent` must not inspect target resources to emulate tool behavior.
   - For approval UX, loop invokes tool hook and renders returned text.
4. Loop guards/policies are allowed only when tool-agnostic.
   - Keep: max step limits, malformed response retries, required-arg validation.
   - Avoid: tool-specific mutation heuristics hardcoded in loop.

## Consequences

### Positive

- Cleaner boundaries: filesystem awareness stays in tool adapters.
- Better extensibility: new mutation tools can plug approval context without touching loop core.
- Lower regression risk: fewer special branches in `LLMAgent`.

### Tradeoffs

- Tool contract surface increases (`build_approval_context` hook).
- Tool authors must maintain preview quality for their own mutation tools.
- Loop still depends on optional hook presence; missing hook means less rich approval context.

## Implementation Notes

- `BaseTool` provides default no-op hook:
  - `build_approval_context(**kwargs) -> str`
- `FileWriteTool` and `FileEditTool` implement unified-diff previews in tool layer.
- `LLMAgent` consumes tool hook output in approval description build path.
