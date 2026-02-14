"""Top-level v1 API router."""

from __future__ import annotations

from fastapi import APIRouter

from .endpoints.approvals import router as approvals_router
from .endpoints.runs import router as runs_router
from .endpoints.sessions import router as sessions_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(sessions_router)
api_v1_router.include_router(runs_router)
api_v1_router.include_router(approvals_router)
