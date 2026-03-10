"""Single-agent factory helpers."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .agent import AgentConfig, ResumeAgent
from .llm import LLMConfig, load_config


def create_agent(
    llm_config: Optional[LLMConfig] = None,
    agent_config: Optional[AgentConfig] = None,
    workspace_dir: str = ".",
    session_manager: Optional[Any] = None,
    verbose: bool = False,
    tools: Optional[Dict] = None,
) -> ResumeAgent:
    """Create the single-agent runtime."""
    if llm_config is None:
        llm_config = load_config()

    return ResumeAgent(
        llm_config=llm_config,
        agent_config=agent_config or AgentConfig(workspace_dir=workspace_dir, verbose=verbose),
        session_manager=session_manager,
        tools=tools,
    )


__all__ = ["create_agent"]
