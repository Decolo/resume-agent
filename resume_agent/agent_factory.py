"""Compatibility wrapper for agent-factory orchestration during monorepo migration."""

from __future__ import annotations

from packages.core.resume_agent_core.agent_factory import (
    AutoAgent,
    IntentRouter,
    MultiAgentConfig,
    create_agent,
    create_multi_agent_system,
    load_multi_agent_config,
)

__all__ = [
    "AutoAgent",
    "IntentRouter",
    "MultiAgentConfig",
    "create_agent",
    "create_multi_agent_system",
    "load_multi_agent_config",
]
