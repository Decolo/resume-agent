"""Compatibility wrapper for ResumeAgent during monorepo migration."""

from __future__ import annotations

from packages.core.resume_agent_core.agent import AgentConfig, ResumeAgent, main

__all__ = ["AgentConfig", "ResumeAgent", "main"]
