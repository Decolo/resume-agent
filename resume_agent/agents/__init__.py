"""Multi-agent system for Resume Agent.

This package implements a sophisticated multi-agent orchestration system where
specialized agents (Parser, Writer, Formatter) can delegate tasks to each other,
coordinated by an Orchestrator agent.
"""

from .agent_tool import AgentTool
from .base import BaseAgent
from .context import SharedContext
from .delegation import DelegationManager
from .formatter_agent import FormatterAgent
from .history import MultiAgentHistoryManager
from .orchestrator_agent import OrchestratorAgent
from .parser_agent import ParserAgent
from .protocol import AgentResult, AgentTask, generate_task_id
from .registry import AgentRegistry
from .writer_agent import WriterAgent

__all__ = [
    "AgentTask",
    "AgentResult",
    "generate_task_id",
    "BaseAgent",
    "AgentRegistry",
    "DelegationManager",
    "SharedContext",
    "MultiAgentHistoryManager",
    "AgentTool",
    "ParserAgent",
    "WriterAgent",
    "FormatterAgent",
    "OrchestratorAgent",
]
