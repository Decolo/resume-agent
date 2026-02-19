"""Dependency providers for v1 API."""

from __future__ import annotations

from fastapi import Request

from ...store_protocol import RuntimeStore


def get_store(request: Request) -> RuntimeStore:
    """Access shared runtime store from app state."""
    return request.app.state.runtime_store


def get_tenant_id(request: Request) -> str:
    """Return tenant identifier resolved by auth middleware."""
    tenant_id = getattr(request.state, "tenant_id", None)
    return tenant_id or "local-dev"
