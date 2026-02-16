"""Compatibility wrapper for API app entrypoint during monorepo migration."""

from __future__ import annotations

from apps.api.resume_agent_api.app import InMemoryRateLimiter, app, create_app, main

__all__ = ["InMemoryRateLimiter", "app", "create_app", "main"]
