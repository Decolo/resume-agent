"""Delegation manager for multi-agent system."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, TYPE_CHECKING

from .protocol import AgentTask, AgentResult, create_result

if TYPE_CHECKING:
    from .base import BaseAgent
    from .registry import AgentRegistry
    from ..observability import AgentObserver

logger = logging.getLogger(__name__)


class DelegationCycleError(Exception):
    """Raised when a delegation cycle is detected."""

    pass


class MaxDelegationDepthError(Exception):
    """Raised when maximum delegation depth is exceeded."""

    pass


class NoDelegateFoundError(Exception):
    """Raised when no suitable agent is found for delegation."""

    pass


@dataclass
class DelegationConfig:
    """Configuration for delegation behavior."""

    max_depth: int = 5
    timeout_seconds: float = 300.0
    enable_cycle_detection: bool = True
    max_delegations_per_task: int = 10


@dataclass
class DelegationRecord:
    """Record of a single delegation."""

    task_id: str
    from_agent: str
    to_agent: str
    timestamp: float
    duration_ms: Optional[float] = None
    success: Optional[bool] = None


class DelegationManager:
    """Manages agent-to-agent delegation with safety mechanisms.

    Features:
    - Cycle detection using DFS algorithm
    - Maximum delegation depth enforcement
    - Timeout handling
    - Delegation history tracking
    - Performance metrics

    Example:
        manager = DelegationManager(registry, observer)

        # Delegate a task
        result = await manager.delegate(task, from_agent="orchestrator")

        # Get delegation chain
        chain = manager.get_delegation_chain(task_id)

        # Print delegation tree
        manager.print_delegation_tree(root_task_id)
    """

    def __init__(
        self,
        registry: AgentRegistry,
        observer: Optional[AgentObserver] = None,
        config: Optional[DelegationConfig] = None,
    ):
        """Initialize the delegation manager.

        Args:
            registry: Agent registry for finding agents
            observer: Observer for logging and metrics
            config: Delegation configuration
        """
        self.registry = registry
        self.observer = observer
        self.config = config or DelegationConfig()

        # Delegation tracking
        self._delegation_graph: Dict[str, List[str]] = {}  # task_id -> [child_task_ids]
        self._delegation_history: List[DelegationRecord] = []
        self._active_delegations: Set[str] = set()  # Currently executing task_ids

    async def delegate(
        self,
        task: AgentTask,
        from_agent: str,
        to_agent: Optional[str] = None,
    ) -> AgentResult:
        """Delegate a task to an appropriate agent.

        Args:
            task: The task to delegate
            from_agent: ID of the agent delegating the task
            to_agent: Optional specific agent to delegate to (if None, auto-select)

        Returns:
            AgentResult from the delegated agent

        Raises:
            DelegationCycleError: If a delegation cycle is detected
            MaxDelegationDepthError: If max delegation depth is exceeded
            NoDelegateFoundError: If no suitable agent is found
            asyncio.TimeoutError: If delegation times out
        """
        start_time = time.time()

        # Check delegation depth
        if task.max_depth <= 0:
            raise MaxDelegationDepthError(
                f"Maximum delegation depth ({self.config.max_depth}) exceeded"
            )

        # Check for cycles
        if self.config.enable_cycle_detection:
            if self._detect_cycle(task, from_agent):
                raise DelegationCycleError(
                    f"Delegation cycle detected for task {task.task_id}"
                )

        # Find target agent
        if to_agent:
            target_agent = self.registry.get_agent(to_agent)
            if not target_agent:
                raise NoDelegateFoundError(f"Agent '{to_agent}' not found")
        else:
            target_agent = self.registry.find_best_agent(task)
            if not target_agent:
                raise NoDelegateFoundError(
                    f"No suitable agent found for task type '{task.task_type}'"
                )

        # Record delegation
        record = DelegationRecord(
            task_id=task.task_id,
            from_agent=from_agent,
            to_agent=target_agent.agent_id,
            timestamp=start_time,
        )
        self._delegation_history.append(record)

        # Update delegation graph
        if task.parent_task_id:
            if task.parent_task_id not in self._delegation_graph:
                self._delegation_graph[task.parent_task_id] = []
            self._delegation_graph[task.parent_task_id].append(task.task_id)

        # Track active delegation
        self._active_delegations.add(task.task_id)

        # Update agent stats
        from_agent_obj = self.registry.get_agent(from_agent)
        if from_agent_obj:
            from_agent_obj.stats.delegations_made += 1
        target_agent.stats.delegations_received += 1

        logger.info(
            f"Delegating task '{task.task_id}' ({task.task_type}) "
            f"from '{from_agent}' to '{target_agent.agent_id}'"
        )

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                target_agent.execute_with_tracking(task),
                timeout=self.config.timeout_seconds,
            )

            # Update record
            record.duration_ms = (time.time() - start_time) * 1000
            record.success = result.success

            # Log to observer
            if self.observer:
                self._log_delegation(record)

            return result

        except asyncio.TimeoutError:
            record.duration_ms = self.config.timeout_seconds * 1000
            record.success = False

            logger.error(
                f"Delegation timeout for task '{task.task_id}' "
                f"after {self.config.timeout_seconds}s"
            )

            return create_result(
                task_id=task.task_id,
                agent_id=target_agent.agent_id,
                success=False,
                output="",
                execution_time_ms=record.duration_ms,
                error=f"Delegation timed out after {self.config.timeout_seconds}s",
            )

        except Exception as e:
            record.duration_ms = (time.time() - start_time) * 1000
            record.success = False

            logger.error(f"Delegation failed for task '{task.task_id}': {e}")

            return create_result(
                task_id=task.task_id,
                agent_id=target_agent.agent_id,
                success=False,
                output="",
                execution_time_ms=record.duration_ms,
                error=str(e),
            )

        finally:
            self._active_delegations.discard(task.task_id)

    def _detect_cycle(self, task: AgentTask, from_agent: str) -> bool:
        """Detect cycles in the delegation graph using DFS.

        Args:
            task: The task being delegated
            from_agent: The agent delegating the task

        Returns:
            True if a cycle is detected, False otherwise
        """
        # Build a path from root to current task
        path: List[str] = []
        current_task_id = task.parent_task_id

        while current_task_id:
            if current_task_id in path:
                # Found a cycle in the task chain
                return True
            path.append(current_task_id)

            # Find parent of current task
            parent_found = False
            for parent_id, children in self._delegation_graph.items():
                if current_task_id in children:
                    current_task_id = parent_id
                    parent_found = True
                    break

            if not parent_found:
                break

        # Check if we're delegating back to an agent already in the chain
        # by looking at delegation history
        visited_agents: Set[str] = {from_agent}
        current_task_id = task.parent_task_id

        for record in reversed(self._delegation_history):
            if record.task_id == current_task_id:
                if record.to_agent in visited_agents:
                    return True
                visited_agents.add(record.from_agent)
                visited_agents.add(record.to_agent)
                current_task_id = None

                # Find parent task
                for parent_id, children in self._delegation_graph.items():
                    if record.task_id in children:
                        current_task_id = parent_id
                        break

        return False

    def get_delegation_chain(self, task_id: str) -> List[DelegationRecord]:
        """Get the delegation chain for a task.

        Args:
            task_id: ID of the task

        Returns:
            List of delegation records in the chain
        """
        chain = []

        # Find all records related to this task
        for record in self._delegation_history:
            if record.task_id == task_id:
                chain.append(record)

        # Find child delegations
        child_task_ids = self._delegation_graph.get(task_id, [])
        for child_id in child_task_ids:
            chain.extend(self.get_delegation_chain(child_id))

        return chain

    def get_delegation_tree(self, root_task_id: str) -> Dict:
        """Get the delegation tree as a nested dictionary.

        Args:
            root_task_id: ID of the root task

        Returns:
            Nested dictionary representing the delegation tree
        """
        # Find the record for this task
        record = None
        for r in self._delegation_history:
            if r.task_id == root_task_id:
                record = r
                break

        tree = {
            "task_id": root_task_id,
            "from_agent": record.from_agent if record else "unknown",
            "to_agent": record.to_agent if record else "unknown",
            "duration_ms": record.duration_ms if record else None,
            "success": record.success if record else None,
            "children": [],
        }

        # Add children
        child_task_ids = self._delegation_graph.get(root_task_id, [])
        for child_id in child_task_ids:
            tree["children"].append(self.get_delegation_tree(child_id))

        return tree

    def print_delegation_tree(self, root_task_id: str, indent: int = 0) -> str:
        """Generate ASCII representation of delegation tree.

        Args:
            root_task_id: ID of the root task
            indent: Current indentation level

        Returns:
            ASCII tree representation
        """
        tree = self.get_delegation_tree(root_task_id)
        return self._format_tree_node(tree, indent)

    def _format_tree_node(self, node: Dict, indent: int = 0) -> str:
        """Format a single tree node.

        Args:
            node: Tree node dictionary
            indent: Current indentation level

        Returns:
            Formatted string for this node and its children
        """
        prefix = "│   " * indent
        connector = "├── " if indent > 0 else ""

        status = "✓" if node["success"] else "✗" if node["success"] is False else "?"
        duration = f"[{node['duration_ms']:.0f}ms]" if node["duration_ms"] else ""

        line = (
            f"{prefix}{connector}{node['task_id']} "
            f"({node['from_agent']} → {node['to_agent']}) "
            f"{duration} {status}\n"
        )

        for i, child in enumerate(node["children"]):
            is_last = i == len(node["children"]) - 1
            child_prefix = "└── " if is_last else "├── "
            line += self._format_tree_node(child, indent + 1)

        return line

    def _log_delegation(self, record: DelegationRecord) -> None:
        """Log delegation to observer.

        Note: Tool execution is already logged by llm.py, so we only
        log delegation-specific info at DEBUG level to avoid duplicates.

        Args:
            record: The delegation record to log
        """
        # Don't log to observer - llm.py already logs tool calls
        # Just log at debug level for tracing
        logger.debug(
            f"Delegation completed: {record.from_agent} → {record.to_agent} "
            f"({record.duration_ms:.0f}ms, success={record.success})"
        )

    def get_stats(self) -> Dict:
        """Get delegation statistics.

        Returns:
            Dictionary with delegation statistics
        """
        total_delegations = len(self._delegation_history)
        successful = sum(1 for r in self._delegation_history if r.success)
        failed = sum(1 for r in self._delegation_history if r.success is False)
        pending = sum(1 for r in self._delegation_history if r.success is None)

        total_duration = sum(
            r.duration_ms for r in self._delegation_history if r.duration_ms
        )
        avg_duration = total_duration / total_delegations if total_delegations else 0

        return {
            "total_delegations": total_delegations,
            "successful": successful,
            "failed": failed,
            "pending": pending,
            "success_rate": f"{successful / total_delegations * 100:.1f}%"
            if total_delegations
            else "N/A",
            "average_duration_ms": f"{avg_duration:.1f}ms",
            "active_delegations": len(self._active_delegations),
        }

    def clear_history(self) -> None:
        """Clear delegation history."""
        self._delegation_graph.clear()
        self._delegation_history.clear()
        self._active_delegations.clear()
        logger.info("Cleared delegation history")

    def __repr__(self) -> str:
        return (
            f"DelegationManager("
            f"total_delegations={len(self._delegation_history)}, "
            f"active={len(self._active_delegations)})"
        )
