# Architecture Decision Records (ADRs)

This directory contains lightweight architecture decision records documenting key technical choices in the resume-agent project.

## Format

Each ADR follows this structure:
- **Status**: Accepted | Superseded | Deprecated
- **Context**: What problem are we solving?
- **Decision**: What did we decide?
- **Consequences**: What are the tradeoffs?

## Index

- [ADR-001: Gemini Function Calling Format](./001-gemini-function-calling.md) - Why we convert OpenAI format to Gemini types
- [ADR-003: Agent Loop and Tool Responsibility Boundary](./003-agent-loop-tool-boundary.md) - Keep loop orchestration generic; mutation semantics and approval previews live in tools

## Creating New ADRs

When making significant architectural decisions:
1. Create `NNN-short-title.md` with next number
2. Document context, decision, and consequences
3. Update this index
4. Keep it concise (1-2 pages max)
