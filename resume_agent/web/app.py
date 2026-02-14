"""FastAPI app entrypoint for Resume Agent web APIs."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from time import perf_counter
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from .api.v1.router import api_v1_router
from .errors import APIError, api_error_handler, validation_error_handler
from .store import InMemoryRuntimeStore
from .workspace import RemoteWorkspaceProvider

logger = logging.getLogger("resume_agent.web.api")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    workspace_root = Path(
        os.getenv("RESUME_AGENT_WEB_WORKSPACE_ROOT", "workspace/web_sessions")
    ).resolve()
    workspace_provider = RemoteWorkspaceProvider(workspace_root)
    store = InMemoryRuntimeStore(
        workspace_provider=workspace_provider,
        provider_name=os.getenv("RESUME_AGENT_DEFAULT_PROVIDER", "stub"),
        model_name=os.getenv("RESUME_AGENT_DEFAULT_MODEL", "stub-model"),
    )

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

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        start = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (perf_counter() - start) * 1000
            path_params = request.scope.get("path_params", {})
            meta = store.runtime_metadata()
            logger.info(
                "api_request method=%s path=%s status=%s duration_ms=%.2f session_id=%s run_id=%s provider=%s model=%s",
                request.method,
                request.url.path,
                500,
                duration_ms,
                path_params.get("session_id", "-"),
                path_params.get("run_id", "-"),
                meta["provider"],
                meta["model"],
            )
            raise

        duration_ms = (perf_counter() - start) * 1000
        path_params = request.scope.get("path_params", {})
        meta = store.runtime_metadata()
        logger.info(
            "api_request method=%s path=%s status=%s duration_ms=%.2f session_id=%s run_id=%s provider=%s model=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            path_params.get("session_id", "-"),
            path_params.get("run_id", "-"),
            meta["provider"],
            meta["model"],
        )
        return response

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
