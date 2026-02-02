"""Multi-agent system for Resume Agent.

This package implements a sophisticated multi-agent orchestration system where
specialized agents (Parser, Writer, Formatter) can delegate tasks to each other,
coordinated by an Orchestrator agent.
"""

from .protocol import AgentTask, AgentResult, generate_task_id
from .base import BaseAgent
from .registry import AgentRegistry
from .delegation import DelegationManager
from .context import SharedContext
from .history import MultiAgentHistoryManager
from .agent_tool import AgentTool
from .parser_agent import ParserAgent
from .writer_agent import WriterAgent
from .formatter_agent import FormatterAgent
from .orchestrator_agent import OrchestratorAgent

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
