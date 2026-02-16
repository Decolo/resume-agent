"""FastAPI app entrypoint for Resume Agent web APIs."""

from __future__ import annotations

import logging
import os
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from hmac import compare_digest
from pathlib import Path
from time import monotonic, perf_counter
from typing import Any, Dict, List

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api.v1.router import api_v1_router
from .artifact_storage import LocalArtifactStorageProvider
from .errors import APIError, api_error_handler, validation_error_handler
from .store import InMemoryRuntimeStore
from .workspace import RemoteWorkspaceProvider

logger = logging.getLogger("resume_agent.web.api")


class InMemoryRateLimiter:
    """Simple fixed-window limiter keyed by tenant id."""

    def __init__(self, max_requests_per_minute: int) -> None:
        self._max_requests = max_requests_per_minute
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, tenant_id: str) -> bool:
        now = monotonic()
        window_start = now - 60
        queue = self._events[tenant_id]
        while queue and queue[0] < window_start:
            queue.popleft()
        if len(queue) >= self._max_requests:
            return False
        queue.append(now)
        return True


def _api_error_response(status_code: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    err = APIError(status_code=status_code, code=code, message=message, details=details)
    return JSONResponse(status_code=err.status_code, content=err.to_dict())


def _parse_fallback_chain(value: str) -> List[Dict[str, str]]:
    chain: List[Dict[str, str]] = []
    for item in (value or "").split(","):
        raw = item.strip()
        if not raw:
            continue
        if ":" not in raw:
            continue
        provider, model = raw.split(":", 1)
        provider = provider.strip()
        model = model.strip()
        if provider and model:
            chain.append({"provider": provider, "model": model})
    return chain


def _resolve_ui_dir() -> Path:
    """Resolve UI directory from monorepo apps/web source."""
    repo_root = Path(__file__).resolve().parents[3]
    apps_web_ui_dir = repo_root / "apps" / "web" / "ui"
    if apps_web_ui_dir.exists():
        return apps_web_ui_dir
    return Path(__file__).resolve().parent / "ui"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    ui_dir = _resolve_ui_dir()
    auth_mode = os.getenv("RESUME_AGENT_WEB_AUTH_MODE", "off").strip().lower()
    api_token = os.getenv("RESUME_AGENT_WEB_API_TOKEN", "").strip()
    max_requests_per_minute = int(os.getenv("RESUME_AGENT_WEB_RATE_LIMIT_RPM", "300"))
    max_runs_per_session = int(os.getenv("RESUME_AGENT_WEB_MAX_RUNS_PER_SESSION", "100"))
    max_upload_bytes = int(os.getenv("RESUME_AGENT_WEB_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
    cost_per_million_tokens = float(os.getenv("RESUME_AGENT_WEB_COST_PER_MILLION_TOKENS", "0.08"))
    session_ttl_seconds = int(os.getenv("RESUME_AGENT_WEB_SESSION_TTL_SECONDS", "0"))
    artifact_ttl_seconds = int(os.getenv("RESUME_AGENT_WEB_ARTIFACT_TTL_SECONDS", "0"))
    cleanup_interval_seconds = int(os.getenv("RESUME_AGENT_WEB_CLEANUP_INTERVAL_SECONDS", "300"))
    state_file_env = os.getenv("RESUME_AGENT_WEB_STATE_FILE", "").strip()
    provider_retry_max_attempts = int(os.getenv("RESUME_AGENT_WEB_PROVIDER_RETRY_MAX_ATTEMPTS", "3"))
    provider_retry_base_delay_seconds = float(os.getenv("RESUME_AGENT_WEB_PROVIDER_RETRY_BASE_DELAY_SECONDS", "1.0"))
    provider_retry_max_delay_seconds = float(os.getenv("RESUME_AGENT_WEB_PROVIDER_RETRY_MAX_DELAY_SECONDS", "30.0"))
    provider_fallback_chain = _parse_fallback_chain(os.getenv("RESUME_AGENT_WEB_PROVIDER_FALLBACK_CHAIN", ""))
    alert_max_error_rate = float(os.getenv("RESUME_AGENT_WEB_ALERT_MAX_ERROR_RATE", "0.2"))
    alert_max_p95_latency_ms = float(os.getenv("RESUME_AGENT_WEB_ALERT_MAX_P95_LATENCY_MS", "15000"))
    alert_max_total_cost_usd = float(os.getenv("RESUME_AGENT_WEB_ALERT_MAX_TOTAL_COST_USD", "10"))
    alert_max_queue_depth = float(os.getenv("RESUME_AGENT_WEB_ALERT_MAX_QUEUE_DEPTH", "50"))
    allowed_upload_mime_types = [
        item.strip()
        for item in os.getenv(
            "RESUME_AGENT_WEB_ALLOWED_UPLOAD_MIME_TYPES",
            "text/markdown,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ).split(",")
        if item.strip()
    ]

    workspace_root = Path(os.getenv("RESUME_AGENT_WEB_WORKSPACE_ROOT", "workspace/web_sessions")).resolve()
    artifact_root = Path(os.getenv("RESUME_AGENT_WEB_ARTIFACT_ROOT", "workspace/web_artifacts")).resolve()
    state_file = Path(state_file_env).resolve() if state_file_env else None
    workspace_provider = RemoteWorkspaceProvider(workspace_root)
    artifact_provider = LocalArtifactStorageProvider(artifact_root)
    provider_error_policy: Dict[str, Any] = {
        "retry": {
            "max_attempts": max(provider_retry_max_attempts, 1),
            "base_delay_seconds": max(provider_retry_base_delay_seconds, 0.0),
            "max_delay_seconds": max(provider_retry_max_delay_seconds, 0.0),
        },
        "fallback_chain": provider_fallback_chain,
    }
    alert_thresholds: Dict[str, float] = {
        "max_error_rate": max(alert_max_error_rate, 0.0),
        "max_p95_latency_ms": max(alert_max_p95_latency_ms, 0.0),
        "max_total_cost_usd": max(alert_max_total_cost_usd, 0.0),
        "max_queue_depth": max(alert_max_queue_depth, 0.0),
    }
    store = InMemoryRuntimeStore(
        workspace_provider=workspace_provider,
        artifact_storage_provider=artifact_provider,
        provider_name=os.getenv("RESUME_AGENT_DEFAULT_PROVIDER", "stub"),
        model_name=os.getenv("RESUME_AGENT_DEFAULT_MODEL", "stub-model"),
        max_runs_per_session=max_runs_per_session,
        max_upload_bytes=max_upload_bytes,
        allowed_upload_mime_types=allowed_upload_mime_types,
        cost_per_million_tokens=cost_per_million_tokens,
        session_ttl_seconds=session_ttl_seconds,
        artifact_ttl_seconds=artifact_ttl_seconds,
        cleanup_interval_seconds=cleanup_interval_seconds,
        provider_error_policy=provider_error_policy,
        state_file=state_file,
        alert_thresholds=alert_thresholds,
    )
    rate_limiter = InMemoryRateLimiter(max_requests_per_minute=max_requests_per_minute)

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
    app.mount("/web/static", StaticFiles(directory=ui_dir), name="web_static")

    @app.middleware("http")
    async def auth_and_tenant_middleware(request: Request, call_next):
        if not request.url.path.startswith("/api/v1"):
            return await call_next(request)

        tenant_id = (request.headers.get("X-Tenant-ID") or "").strip()
        if auth_mode == "token":
            if not api_token:
                return _api_error_response(
                    500,
                    "SERVER_MISCONFIGURED",
                    "API token auth is enabled but token is missing",
                )

            auth_header = (request.headers.get("Authorization") or "").strip()
            if not auth_header.startswith("Bearer "):
                return _api_error_response(401, "UNAUTHORIZED", "Missing bearer token")
            token = auth_header[len("Bearer ") :].strip()
            if not compare_digest(token, api_token):
                return _api_error_response(401, "UNAUTHORIZED", "Invalid bearer token")
            if not tenant_id:
                return _api_error_response(400, "BAD_REQUEST", "X-Tenant-ID header is required")
        else:
            tenant_id = tenant_id or "local-dev"

        if not rate_limiter.allow(tenant_id):
            return _api_error_response(
                429,
                "RATE_LIMITED",
                "Request rate limit exceeded",
                {"limit_per_minute": max_requests_per_minute},
            )

        request.state.tenant_id = tenant_id
        return await call_next(request)

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
                "api_request method=%s path=%s status=%s duration_ms=%.2f session_id=%s run_id=%s provider=%s model=%s retry_max_attempts=%s fallback_chain_size=%s",
                request.method,
                request.url.path,
                500,
                duration_ms,
                path_params.get("session_id", "-"),
                path_params.get("run_id", "-"),
                meta["provider"],
                meta["model"],
                meta.get("retry_max_attempts", "-"),
                meta.get("fallback_chain_size", "-"),
            )
            raise

        duration_ms = (perf_counter() - start) * 1000
        path_params = request.scope.get("path_params", {})
        meta = store.runtime_metadata()
        logger.info(
            "api_request method=%s path=%s status=%s duration_ms=%.2f session_id=%s run_id=%s provider=%s model=%s retry_max_attempts=%s fallback_chain_size=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            path_params.get("session_id", "-"),
            path_params.get("run_id", "-"),
            meta["provider"],
            meta["model"],
            meta.get("retry_max_attempts", "-"),
            meta.get("fallback_chain_size", "-"),
        )
        return response

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/web")

    @app.get("/web", include_in_schema=False)
    async def web_ui() -> FileResponse:
        return FileResponse(ui_dir / "index.html")

    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    return app


app = create_app()


def main() -> None:
    """Run development API server."""
    import uvicorn

    uvicorn.run("apps.api.resume_agent_api.app:app", host="127.0.0.1", port=8000)
