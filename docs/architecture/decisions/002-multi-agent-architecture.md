# ADR-002: Multi-Agent Architecture with Three Operational Modes

**Status**: Accepted

**Date**: 2024-02 (Phase 2 implementation)

## Context

As resume-agent grew, single-agent mode became a bottleneck for complex workflows:
- Parsing large PDFs + analyzing + rewriting + formatting in one agent was slow
- No parallelization of independent tasks
- Hard to optimize prompts for different subtasks

We needed a way to decompose work while maintaining simplicity for basic use cases.

## Decision

Implement **three operational modes** controlled by `multi_agent.enabled` in config:

1. **`false` (default)**: Single-agent mode
   - `ResumeAgent` handles everything with all tools
   - Simple, predictable, good for basic tasks

2. **`true`**: Multi-agent mode
   - `OrchestratorAgent` delegates to specialized agents:
     - `ParserAgent`: resume parsing (least privilege: parse, read, list)
     - `WriterAgent`: content generation (read, write)
     - `FormatterAgent`: output formatting (resume_write, read, write)
   - Agents wrapped as tools via `AgentTool`
   - Isolated history per agent via `MultiAgentHistoryManager`

3. **`"auto"`**: Automatic routing
   - `AutoAgent` uses `IntentRouter` (LLM classifier + regex heuristics)
   - Routes to multi-agent when: multiple formats, batch keywords, multiple files
   - Routes to single-agent for simple requests

Entry point: `agent_factory.create_agent()` returns appropriate agent type.

## Consequences

### Positive
- **Specialization**: Each agent has focused prompts and minimal tool access
- **Least privilege**: Agents only get tools they need (security + clarity)
- **Parallelization potential**: Independent tasks can run concurrently
- **Backward compatibility**: Single-agent mode unchanged
- **Flexibility**: Users can choose mode based on needs

### Negative
- **Complexity**: Three code paths to maintain
- **Delegation overhead**: Multi-agent adds LLM calls for routing
- **Context isolation**: Agents don't share history, context passed explicitly via `AgentTask.context`
- **Debugging harder**: Multi-agent failures require tracing across agents

### Implementation Details
- `DelegationManager` handles routing with DFS cycle detection (max depth 5)
- `AgentRegistry` scores agents: 50% capability match + 30% success rate + 20% load
- Each agent has isolated `HistoryManager` to prevent cross-contamination

## Alternatives Considered

1. **Always multi-agent**: Would add overhead for simple tasks
2. **Always single-agent**: Would limit scalability for complex workflows
3. **Manual mode selection**: Auto mode provides better UX

## References
- `resume_agent/agent_factory.py` - Agent creation and routing
- `resume_agent/agents/` - Specialized agent implementations
- `resume_agent/agents/delegation.py` - DelegationManager
- `resume_agent/agents/protocol.py` - AgentTask/AgentResult contracts
