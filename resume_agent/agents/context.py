"""Shared context for multi-agent communication."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ContextUpdate:
    """Record of a context update."""

    key: str
    value: Any
    agent_id: str
    timestamp: float
    previous_value: Optional[Any] = None


class SharedContext:
    """Shared context that flows between agents during task execution.

    The SharedContext provides:
    - Key-value storage for inter-agent data sharing
    - History tracking of all updates
    - Merge capability for combining contexts
    - Agent attribution for each update

    Example:
        context = SharedContext()

        # Set values
        context.set("parsed_resume", resume_data, agent_id="parser")
        context.set("improved_content", content, agent_id="writer")

        # Get values
        resume = context.get("parsed_resume")

        # Merge contexts
        context.merge(other_context)

        # Get history
        history = context.get_history()
    """

    def __init__(self, initial_data: Optional[Dict[str, Any]] = None):
        """Initialize the shared context.

        Args:
            initial_data: Optional initial data to populate the context
        """
        self._data: Dict[str, Any] = {}
        self._history: List[ContextUpdate] = []

        if initial_data:
            for key, value in initial_data.items():
                self._data[key] = value

    def set(self, key: str, value: Any, agent_id: str = "unknown") -> None:
        """Set a value in the context.

        Args:
            key: The key to set
            value: The value to store
            agent_id: ID of the agent making the update
        """
        previous_value = self._data.get(key)

        self._data[key] = value

        # Record the update
        self._history.append(
            ContextUpdate(
                key=key,
                value=value,
                agent_id=agent_id,
                timestamp=time.time(),
                previous_value=previous_value,
            )
        )

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the context.

        Args:
            key: The key to retrieve
            default: Default value if key not found

        Returns:
            The value, or default if not found
        """
        return self._data.get(key, default)

    def has(self, key: str) -> bool:
        """Check if a key exists in the context.

        Args:
            key: The key to check

        Returns:
            True if the key exists, False otherwise
        """
        return key in self._data

    def delete(self, key: str, agent_id: str = "unknown") -> Optional[Any]:
        """Delete a key from the context.

        Args:
            key: The key to delete
            agent_id: ID of the agent making the deletion

        Returns:
            The deleted value, or None if key didn't exist
        """
        if key in self._data:
            value = self._data.pop(key)

            # Record the deletion
            self._history.append(
                ContextUpdate(
                    key=key,
                    value=None,
                    agent_id=agent_id,
                    timestamp=time.time(),
                    previous_value=value,
                )
            )

            return value

        return None

    def keys(self) -> List[str]:
        """Get all keys in the context.

        Returns:
            List of all keys
        """
        return list(self._data.keys())

    def values(self) -> List[Any]:
        """Get all values in the context.

        Returns:
            List of all values
        """
        return list(self._data.values())

    def items(self) -> List[tuple]:
        """Get all key-value pairs in the context.

        Returns:
            List of (key, value) tuples
        """
        return list(self._data.items())

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to a dictionary.

        Returns:
            Dictionary copy of the context data
        """
        return self._data.copy()

    def merge(self, other: SharedContext, agent_id: str = "unknown") -> None:
        """Merge another context into this one.

        Values from the other context will overwrite existing values.

        Args:
            other: The context to merge from
            agent_id: ID of the agent performing the merge
        """
        for key, value in other._data.items():
            self.set(key, value, agent_id=agent_id)

    def get_history(self) -> List[ContextUpdate]:
        """Get the history of all context updates.

        Returns:
            List of ContextUpdate records
        """
        return self._history.copy()

    def get_history_for_key(self, key: str) -> List[ContextUpdate]:
        """Get the history of updates for a specific key.

        Args:
            key: The key to get history for

        Returns:
            List of ContextUpdate records for the key
        """
        return [update for update in self._history if update.key == key]

    def get_history_by_agent(self, agent_id: str) -> List[ContextUpdate]:
        """Get the history of updates made by a specific agent.

        Args:
            agent_id: The agent ID to filter by

        Returns:
            List of ContextUpdate records from the agent
        """
        return [update for update in self._history if update.agent_id == agent_id]

    def clear(self) -> None:
        """Clear all data and history."""
        self._data.clear()
        self._history.clear()

    def clear_history(self) -> None:
        """Clear only the history, keeping the data."""
        self._history.clear()

    def copy(self) -> SharedContext:
        """Create a copy of this context.

        Returns:
            New SharedContext with copied data (history is not copied)
        """
        return SharedContext(initial_data=self._data.copy())

    def __len__(self) -> int:
        """Return the number of items in the context."""
        return len(self._data)

    def __contains__(self, key: str) -> bool:
        """Check if a key exists in the context."""
        return key in self._data

    def __getitem__(self, key: str) -> Any:
        """Get a value using bracket notation."""
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """Set a value using bracket notation."""
        self.set(key, value)

    def __repr__(self) -> str:
        return f"SharedContext(keys={list(self._data.keys())}, history_len={len(self._history)})"
