"""Compatibility checks for Slice C core extraction."""

from __future__ import annotations

from packages.core.resume_agent_core.agent import AgentConfig as PackageAgentConfig
from packages.core.resume_agent_core.agent import ResumeAgent as PackageResumeAgent
from packages.core.resume_agent_core.agent_factory import AutoAgent as PackageAutoAgent
from packages.core.resume_agent_core.agent_factory import create_agent as package_create_agent
from packages.core.resume_agent_core.cache import ToolCache as PackageToolCache
from packages.core.resume_agent_core.llm import HistoryManager as PackageHistoryManager
from packages.core.resume_agent_core.llm import LLMAgent as PackageLLMAgent
from packages.core.resume_agent_core.observability import AgentObserver as PackageAgentObserver
from packages.core.resume_agent_core.preview import PendingWriteManager as PackagePendingWriteManager
from packages.core.resume_agent_core.retry import RetryConfig as PackageRetryConfig
from packages.core.resume_agent_core.session import SessionManager as PackageSessionManager
from resume_agent.agent import AgentConfig, ResumeAgent
from resume_agent.agent_factory import AutoAgent, create_agent
from resume_agent.cache import ToolCache
from resume_agent.llm import HistoryManager, LLMAgent
from resume_agent.observability import AgentObserver
from resume_agent.preview import PendingWriteManager
from resume_agent.retry import RetryConfig
from resume_agent.session import SessionManager


def test_core_runtime_exports_are_compatible_with_package_source() -> None:
    assert AgentConfig is PackageAgentConfig
    assert ResumeAgent is PackageResumeAgent
    assert AutoAgent is PackageAutoAgent
    assert create_agent is package_create_agent
    assert LLMAgent is PackageLLMAgent
    assert HistoryManager is PackageHistoryManager


def test_core_support_exports_are_compatible_with_package_source() -> None:
    assert ToolCache is PackageToolCache
    assert RetryConfig is PackageRetryConfig
    assert AgentObserver is PackageAgentObserver
    assert SessionManager is PackageSessionManager
    assert PendingWriteManager is PackagePendingWriteManager
