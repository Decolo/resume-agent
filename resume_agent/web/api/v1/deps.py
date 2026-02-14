"""Dependency providers for v1 API."""

from __future__ import annotations

from fastapi import Request

from ...store import InMemoryRuntimeStore


def get_store(request: Request) -> InMemoryRuntimeStore:
    """Access shared runtime store from app state."""
    return request.app.state.runtime_store

