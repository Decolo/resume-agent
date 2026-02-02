"""Multi-agent history management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from google.genai import types
    from ..llm import HistoryManager
    from .protocol import AgentTask


@dataclass
class HistoryConfig:
    """Configuration for multi-agent history management."""

    strategy: str = "isolated"  # "isolated" or "shared"
    max_messages_per_agent: int = 50
    max_tokens_per_agent: int = 100000


class MultiAgentHistoryManager:
    """Manages conversation histories across multiple agents.

    Supports two strategies:
    1. Isolated: Each agent maintains its own separate history
    2. Shared: All agents share a single history (not recommended)

    The isolated strategy is recommended because:
    - Prevents context pollution between agents
    - Easier to debug individual agent behavior
    - Simpler pruning logic
    - Better token management per agent

    Example:
        manager = MultiAgentHistoryManager(config)

        # Get history for a specific agent
        history = manager.get_agent_history("parser_agent")

        # Add message to agent's history
        manager.add_to_agent("parser_agent", message)

        # Add to master history (orchestrator)
        manager.add_to_master(message)

        # Get context for delegation
        context = manager.get_delegation_context(task)
    """

    def __init__(self, config: Optional[HistoryConfig] = None):
        """Initialize the multi-agent history manager.

        Args:
            config: History configuration
        """
        self.config = config or HistoryConfig()
        self._agent_histories: Dict[str, HistoryManager] = {}
        self._master_history: Optional[HistoryManager] = None

    def _create_history_manager(self) -> HistoryManager:
        """Create a new HistoryManager instance.

        Returns:
            New HistoryManager with configured limits
        """
        # Import here to avoid circular imports
        from ..llm import HistoryManager

        return HistoryManager(
            max_messages=self.config.max_messages_per_agent,
            max_tokens=self.config.max_tokens_per_agent,
        )

    def get_agent_history(self, agent_id: str) -> HistoryManager:
        """Get or create history manager for a specific agent.

        Args:
            agent_id: ID of the agent

        Returns:
            HistoryManager for the agent
        """
        if agent_id not in self._agent_histories:
            self._agent_histories[agent_id] = self._create_history_manager()

        return self._agent_histories[agent_id]

    def get_master_history(self) -> HistoryManager:
        """Get or create the master history (for orchestrator).

        Returns:
            Master HistoryManager
        """
        if self._master_history is None:
            self._master_history = self._create_history_manager()

        return self._master_history

    def add_to_agent(self, agent_id: str, message: types.Content) -> None:
        """Add a message to an agent's history.

        Args:
            agent_id: ID of the agent
            message: The message to add
        """
        history = self.get_agent_history(agent_id)
        history.add_message(message)

    def add_to_master(self, message: types.Content) -> None:
        """Add a message to the master history.

        Args:
            message: The message to add
        """
        master = self.get_master_history()
        master.add_message(message)

    def get_agent_messages(self, agent_id: str) -> List[types.Content]:
        """Get all messages from an agent's history.

        Args:
            agent_id: ID of the agent

        Returns:
            List of messages
        """
        if agent_id not in self._agent_histories:
            return []

        return self._agent_histories[agent_id].get_history()

    def get_master_messages(self) -> List[types.Content]:
        """Get all messages from the master history.

        Returns:
            List of messages
        """
        if self._master_history is None:
            return []

        return self._master_history.get_history()

    def clear_agent_history(self, agent_id: str) -> None:
        """Clear history for a specific agent.

        Args:
            agent_id: ID of the agent
        """
        if agent_id in self._agent_histories:
            self._agent_histories[agent_id].clear()

    def clear_master_history(self) -> None:
        """Clear the master history."""
        if self._master_history:
            self._master_history.clear()

    def clear_all(self) -> None:
        """Clear all histories."""
        for history in self._agent_histories.values():
            history.clear()
        self._agent_histories.clear()

        if self._master_history:
            self._master_history.clear()

    def get_delegation_context(self, task: AgentTask) -> Dict[str, Any]:
        """Extract context for delegation from task and histories.

        This method prepares context data that should be passed
        to a delegated agent, including:
        - Task parameters
        - Relevant data from parent task context
        - Summary of relevant history

        Args:
            task: The task being delegated

        Returns:
            Dictionary with context for the delegated agent
        """
        context = {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "parent_task_id": task.parent_task_id,
            "parameters": task.parameters.copy(),
        }

        # Include task context
        context.update(task.context)

        return context

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics for all histories.

        Returns:
            Dictionary with history statistics
        """
        stats = {
            "agents": {},
            "master": None,
        }

        for agent_id, history in self._agent_histories.items():
            messages = history.get_history()
            stats["agents"][agent_id] = {
                "message_count": len(messages),
                "estimated_tokens": sum(
                    history._estimate_tokens(msg) for msg in messages
                ),
            }

        if self._master_history:
            messages = self._master_history.get_history()
            stats["master"] = {
                "message_count": len(messages),
                "estimated_tokens": sum(
                    self._master_history._estimate_tokens(msg) for msg in messages
                ),
            }

        return stats

    def __repr__(self) -> str:
        return (
            f"MultiAgentHistoryManager("
            f"agents={list(self._agent_histories.keys())}, "
            f"strategy={self.config.strategy!r})"
        )
