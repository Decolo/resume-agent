"""Base agent class for multi-agent system."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .protocol import AgentResult, AgentTask, create_result

if TYPE_CHECKING:
    from ..llm import LLMAgent
    from ..observability import AgentObserver


@dataclass
class AgentConfig:
    """Configuration for a specialized agent."""

    model: str = "gemini-2.5-flash"
    max_tokens: int = 4096
    temperature: float = 0.5
    max_steps: int = 20
    enabled: bool = True


@dataclass
class AgentStats:
    """Statistics for agent performance tracking."""

    tasks_completed: int = 0
    tasks_failed: int = 0
    total_execution_time_ms: float = 0.0
    delegations_made: int = 0
    delegations_received: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate as a percentage."""
        total = self.tasks_completed + self.tasks_failed
        if total == 0:
            return 1.0  # No tasks yet, assume 100%
        return self.tasks_completed / total

    @property
    def average_execution_time_ms(self) -> float:
        """Calculate average execution time per task."""
        total = self.tasks_completed + self.tasks_failed
        if total == 0:
            return 0.0
        return self.total_execution_time_ms / total


class BaseAgent(ABC):
    """Abstract base class for all agents in the multi-agent system.

    Each specialized agent must implement:
    - execute(task): Execute a task and return a result
    - can_handle(task): Check if this agent can handle a given task

    Attributes:
        agent_id: Unique identifier for this agent instance
        agent_type: Type of agent (e.g., "parser", "writer", "formatter", "orchestrator")
        capabilities: List of capabilities this agent provides
        config: Agent configuration
        stats: Performance statistics
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        capabilities: List[str],
        config: Optional[AgentConfig] = None,
        llm_agent: Optional[LLMAgent] = None,
        observer: Optional[AgentObserver] = None,
    ):
        """Initialize the base agent.

        Args:
            agent_id: Unique identifier for this agent
            agent_type: Type of agent
            capabilities: List of capabilities this agent provides
            config: Agent configuration
            llm_agent: The underlying LLM agent for communication
            observer: Observer for logging and metrics
        """
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.capabilities = capabilities
        self.config = config or AgentConfig()
        self.llm_agent = llm_agent
        self.observer = observer
        self.stats = AgentStats()
        self._active_tasks: int = 0
        self._max_concurrent_tasks: int = 5

    @abstractmethod
    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute a task and return the result.

        This method must be implemented by all specialized agents.

        Args:
            task: The task to execute

        Returns:
            AgentResult with the execution outcome
        """
        pass

    @abstractmethod
    def can_handle(self, task: AgentTask) -> bool:
        """Check if this agent can handle the given task.

        Args:
            task: The task to check

        Returns:
            True if this agent can handle the task, False otherwise
        """
        pass

    def capability_match_score(self, task: AgentTask) -> float:
        """Calculate how well this agent's capabilities match the task.

        Args:
            task: The task to score against

        Returns:
            Score between 0.0 and 1.0 indicating match quality
        """
        if task.task_type in self.capabilities:
            return 1.0

        # Check for partial matches in task description
        description_lower = task.description.lower()
        matches = sum(1 for cap in self.capabilities if cap.lower() in description_lower)

        if matches > 0:
            return min(0.8, matches * 0.3)

        return 0.0

    def current_load(self) -> float:
        """Get current load as a percentage (0.0 to 1.0).

        Returns:
            Current load percentage
        """
        return min(1.0, self._active_tasks / self._max_concurrent_tasks)

    def historical_success_rate(self) -> float:
        """Get historical success rate.

        Returns:
            Success rate between 0.0 and 1.0
        """
        return self.stats.success_rate

    async def execute_with_tracking(self, task: AgentTask) -> AgentResult:
        """Execute a task with performance tracking.

        This wrapper method handles:
        - Load tracking
        - Execution timing
        - Statistics updates
        - Error handling

        Args:
            task: The task to execute

        Returns:
            AgentResult with execution outcome
        """
        self._active_tasks += 1
        start_time = time.time()

        try:
            result = await self.execute(task)

            # Update statistics
            execution_time_ms = (time.time() - start_time) * 1000
            result.execution_time_ms = execution_time_ms
            self.stats.total_execution_time_ms += execution_time_ms

            if result.success:
                self.stats.tasks_completed += 1
            else:
                self.stats.tasks_failed += 1

            # Log to observer if available
            if self.observer:
                self.observer.log_step_end(
                    step=self.stats.tasks_completed + self.stats.tasks_failed,
                    duration_ms=execution_time_ms,
                    agent_id=self.agent_id,
                )

            return result

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            self.stats.tasks_failed += 1
            self.stats.total_execution_time_ms += execution_time_ms

            # Log error to observer
            if self.observer:
                self.observer.log_error(
                    error_type=type(e).__name__,
                    message=str(e),
                    context={"agent_id": self.agent_id, "task_id": task.task_id},
                    agent_id=self.agent_id,
                )

            return create_result(
                task_id=task.task_id,
                agent_id=self.agent_id,
                success=False,
                output="",
                execution_time_ms=execution_time_ms,
                error=str(e),
            )

        finally:
            self._active_tasks -= 1

    def get_stats_dict(self) -> Dict[str, Any]:
        """Get agent statistics as a dictionary.

        Returns:
            Dictionary with agent statistics
        """
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "capabilities": self.capabilities,
            "tasks_completed": self.stats.tasks_completed,
            "tasks_failed": self.stats.tasks_failed,
            "success_rate": f"{self.stats.success_rate * 100:.1f}%",
            "average_execution_time_ms": f"{self.stats.average_execution_time_ms:.1f}ms",
            "current_load": f"{self.current_load() * 100:.0f}%",
            "delegations_made": self.stats.delegations_made,
            "delegations_received": self.stats.delegations_received,
        }

    def reset_stats(self):
        """Reset agent statistics."""
        self.stats = AgentStats()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"agent_id={self.agent_id!r}, "
            f"agent_type={self.agent_type!r}, "
            f"capabilities={self.capabilities!r})"
        )
