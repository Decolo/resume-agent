"""Compatibility wrapper for observability helpers during monorepo migration."""

from __future__ import annotations

from packages.core.resume_agent_core.observability import AgentEvent, AgentObserver

__all__ = ["AgentEvent", "AgentObserver"]
