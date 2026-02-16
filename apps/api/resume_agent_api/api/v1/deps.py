"""Dependency providers for v1 API."""

from __future__ import annotations

from fastapi import Request

from ...store import InMemoryRuntimeStore


def get_store(request: Request) -> InMemoryRuntimeStore:
    """Access shared runtime store from app state."""
    return request.app.state.runtime_store


def get_tenant_id(request: Request) -> str:
    """Return tenant identifier resolved by auth middleware."""
    tenant_id = getattr(request.state, "tenant_id", None)
    return tenant_id or "local-dev"
