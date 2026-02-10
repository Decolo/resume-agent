"""Multi-agent history management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from google.genai import types
    from ..llm import HistoryManager


@dataclass
class HistoryConfig:
    """Configuration for multi-agent history management."""

    max_messages_per_agent: int = 50
    max_tokens_per_agent: int = 100000


class MultiAgentHistoryManager:
    """Manages conversation histories across multiple agents.

    Each agent maintains its own isolated history to prevent
    context pollution and simplify token management.

    Example:
        manager = MultiAgentHistoryManager(config)

        # Get history for a specific agent
        history = manager.get_agent_history("parser_agent")

        # Add message to agent's history
        manager.add_to_agent("parser_agent", message)

        # Add to master history (orchestrator)
        manager.add_to_master(message)
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
            f"agents={list(self._agent_histories.keys())})"
        )
