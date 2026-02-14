"""FastAPI app entrypoint for Resume Agent web APIs."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from .api.v1.router import api_v1_router
from .errors import APIError, api_error_handler, validation_error_handler
from .store import InMemoryRuntimeStore


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    store = InMemoryRuntimeStore()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await store.start()
        try:
            yield
        finally:
            await store.stop()

    app = FastAPI(title="Resume Agent API", version="0.1.0", lifespan=lifespan)
    app.state.runtime_store = store
    app.include_router(api_v1_router)

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict:
        return {"status": "ok"}

    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    return app


app = create_app()


def main() -> None:
    """Run development API server."""
    import uvicorn

    uvicorn.run("resume_agent.web.app:app", host="127.0.0.1", port=8000)
