"""Agent registry for multi-agent system."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Optional

from .protocol import AgentTask

if TYPE_CHECKING:
    from .base import BaseAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Central registry for all agents in the multi-agent system.

    The registry provides:
    - Agent registration and discovery
    - Capability-based routing
    - Load-aware agent selection
    - Agent statistics aggregation

    Example:
        registry = AgentRegistry()
        registry.register(parser_agent)
        registry.register(writer_agent)

        # Find agent by ID
        agent = registry.get_agent("parser_agent")

        # Find agents by capability
        agents = registry.find_agents_by_capability("resume_parse")

        # Find best agent for a task
        best_agent = registry.find_best_agent(task)
    """

    def __init__(self):
        """Initialize the agent registry."""
        self._agents: Dict[str, BaseAgent] = {}
        self._capabilities_index: Dict[str, List[str]] = {}  # capability -> [agent_ids]

    def register(self, agent: BaseAgent) -> None:
        """Register an agent with the registry.

        Args:
            agent: The agent to register

        Raises:
            ValueError: If an agent with the same ID is already registered
        """
        if agent.agent_id in self._agents:
            raise ValueError(f"Agent with ID '{agent.agent_id}' is already registered")

        self._agents[agent.agent_id] = agent

        # Index capabilities for fast lookup
        for capability in agent.capabilities:
            if capability not in self._capabilities_index:
                self._capabilities_index[capability] = []
            self._capabilities_index[capability].append(agent.agent_id)

        logger.info(f"Registered agent '{agent.agent_id}' with capabilities: {agent.capabilities}")

    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """Get an agent by its ID.

        Args:
            agent_id: ID of the agent to retrieve

        Returns:
            The agent, or None if not found
        """
        return self._agents.get(agent_id)

    def get_all_agents(self) -> List[BaseAgent]:
        """Get all registered agents.

        Returns:
            List of all registered agents
        """
        return list(self._agents.values())

    def find_agents_by_capability(self, capability: str) -> List[BaseAgent]:
        """Find all agents that have a specific capability.

        Args:
            capability: The capability to search for

        Returns:
            List of agents with the specified capability
        """
        agent_ids = self._capabilities_index.get(capability, [])
        return [self._agents[aid] for aid in agent_ids if aid in self._agents]

    def find_best_agent(self, task: AgentTask) -> Optional[BaseAgent]:
        """Find the best agent to handle a task.

        Uses a scoring algorithm that considers:
        - Capability match (50% weight)
        - Historical success rate (30% weight)
        - Current load (20% weight)

        Args:
            task: The task to find an agent for

        Returns:
            The best agent for the task, or None if no suitable agent found
        """
        candidates = self.find_agents_by_capability(task.task_type)

        if not candidates:
            # Fall back to checking all agents
            candidates = [agent for agent in self._agents.values() if agent.can_handle(task)]

        if not candidates:
            logger.warning(f"No agent found for task type: {task.task_type}")
            return None

        # Score each candidate
        scored_agents = []
        for agent in candidates:
            capability_score = agent.capability_match_score(task)
            success_score = agent.historical_success_rate()
            load_score = 1.0 - agent.current_load()

            # Weighted scoring
            total_score = 0.5 * capability_score + 0.3 * success_score + 0.2 * load_score

            scored_agents.append((agent, total_score))
            logger.debug(
                f"Agent '{agent.agent_id}' scored {total_score:.3f} "
                f"(cap={capability_score:.2f}, success={success_score:.2f}, load={load_score:.2f})"
            )

        # Return highest scoring agent
        best_agent, best_score = max(scored_agents, key=lambda x: x[1])
        logger.info(f"Selected agent '{best_agent.agent_id}' for task '{task.task_type}' with score {best_score:.3f}")

        return best_agent

    def get_stats(self) -> Dict[str, Dict]:
        """Get statistics for all registered agents.

        Returns:
            Dictionary mapping agent IDs to their statistics
        """
        return {agent_id: agent.get_stats_dict() for agent_id, agent in self._agents.items()}

    def __len__(self) -> int:
        """Return the number of registered agents."""
        return len(self._agents)

    def __contains__(self, agent_id: str) -> bool:
        """Check if an agent is registered."""
        return agent_id in self._agents

    def __repr__(self) -> str:
        return (
            f"AgentRegistry(agents={list(self._agents.keys())}, capabilities={list(self._capabilities_index.keys())})"
        )
