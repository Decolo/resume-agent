# ADR-003: FastAPI for Web Backend

**Status**: Accepted

**Date**: 2024-02 (Web productization Phase 1)

## Context

Resume-agent needed a headless web API for:
- Multi-user support with tenant isolation
- Async run execution with SSE streaming
- Approval workflow for file writes
- Session and artifact management

Framework requirements:
- Native async/await support (agent loop is fully async)
- SSE (Server-Sent Events) for real-time updates
- OpenAPI/Swagger docs generation
- Type safety with Pydantic
- Production-ready with good ecosystem

## Decision

Use **FastAPI** as the web framework for the headless backend.

## Consequences

### Positive
- **Native async**: FastAPI is built on Starlette (async ASGI), perfect for our async agent loop
- **Type safety**: Pydantic v2 integration provides request/response validation
- **Auto-generated docs**: OpenAPI schema at `/docs` for free
- **SSE support**: Starlette's `EventSourceResponse` for streaming events
- **Performance**: One of the fastest Python frameworks (benchmarks comparable to Node.js)
- **Developer experience**: Excellent error messages, intuitive API design
- **Ecosystem**: Large community, good middleware options (CORS, auth, etc.)

### Negative
- **Learning curve**: Developers need to understand async/await patterns
- **Dependency weight**: Pulls in Starlette, Pydantic, uvicorn
- **Breaking changes**: FastAPI is pre-1.0, though API is stable

### Implementation Details
- `resume_agent/web/app.py` - FastAPI application with lifespan management
- `resume_agent/web/api/v1/` - Versioned API endpoints
- `resume_agent/web/store.py` - In-memory runtime store with async locks
- SSE streaming via `EventSourceResponse` for run events

## Alternatives Considered

1. **Flask**: Mature but sync-first, would require threading or greenlets
2. **Django**: Too heavyweight, ORM not needed (in-memory store)
3. **Sanic**: Similar to FastAPI but smaller ecosystem
4. **aiohttp**: Lower-level, would require more boilerplate

## References
- `resume_agent/web/app.py` - FastAPI application
- `docs/api-reference/web-api-v1.md` - API contract
- `docs/api-reference/sse-events-v1.md` - SSE event schema
