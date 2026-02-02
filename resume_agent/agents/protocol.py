"""Protocol definitions for multi-agent communication."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def generate_task_id() -> str:
    """Generate a unique task ID."""
    return f"task_{uuid.uuid4().hex[:12]}"


@dataclass
class AgentTask:
    """A task that can be delegated to an agent.

    Attributes:
        task_id: Unique identifier for this task
        task_type: Type of task (e.g., "parse", "write", "format", "analyze")
        description: Human-readable description of the task
        parameters: Task-specific parameters
        context: Shared context across agents
        parent_task_id: ID of parent task (for tracking delegation chains)
        max_depth: Maximum delegation depth to prevent infinite loops
    """

    task_id: str
    task_type: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    parent_task_id: Optional[str] = None
    max_depth: int = 5

    def __post_init__(self):
        """Validate task after initialization."""
        if not self.task_id:
            self.task_id = generate_task_id()
        if self.max_depth < 0:
            raise ValueError("max_depth must be non-negative")

    def create_subtask(
        self,
        task_type: str,
        description: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> AgentTask:
        """Create a subtask from this task.

        Args:
            task_type: Type of the subtask
            description: Description of the subtask
            parameters: Parameters for the subtask

        Returns:
            New AgentTask with this task as parent

        Raises:
            ValueError: If max_depth would be exceeded
        """
        if self.max_depth <= 0:
            raise ValueError("Cannot create subtask: max delegation depth reached")

        return AgentTask(
            task_id=generate_task_id(),
            task_type=task_type,
            description=description,
            parameters=parameters or {},
            context=self.context.copy(),
            parent_task_id=self.task_id,
            max_depth=self.max_depth - 1,
        )


@dataclass
class AgentResult:
    """Result from agent execution.

    Attributes:
        task_id: ID of the task that was executed
        agent_id: ID of the agent that executed the task
        success: Whether the task completed successfully
        output: Output from the task (string or structured data)
        metadata: Additional metadata about the execution
        sub_results: Results from delegated subtasks
        execution_time_ms: Execution time in milliseconds
        error: Error message if task failed
    """

    task_id: str
    agent_id: str
    success: bool
    output: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    sub_results: List[AgentResult] = field(default_factory=list)
    execution_time_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "success": self.success,
            "output": str(self.output),
            "metadata": self.metadata,
            "sub_results": [r.to_dict() for r in self.sub_results],
            "execution_time_ms": self.execution_time_ms,
            "error": self.error,
        }

    def get_total_execution_time(self) -> float:
        """Get total execution time including all subtasks."""
        total = self.execution_time_ms
        for sub_result in self.sub_results:
            total += sub_result.get_total_execution_time()
        return total

    def get_all_errors(self) -> List[str]:
        """Get all errors from this result and subtasks."""
        errors = []
        if self.error:
            errors.append(f"{self.agent_id}: {self.error}")
        for sub_result in self.sub_results:
            errors.extend(sub_result.get_all_errors())
        return errors


def create_task(
    task_type: str,
    description: str,
    parameters: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    max_depth: int = 5,
) -> AgentTask:
    """Helper function to create an AgentTask.

    Args:
        task_type: Type of task
        description: Task description
        parameters: Task parameters
        context: Shared context
        max_depth: Maximum delegation depth

    Returns:
        New AgentTask instance
    """
    return AgentTask(
        task_id=generate_task_id(),
        task_type=task_type,
        description=description,
        parameters=parameters or {},
        context=context or {},
        max_depth=max_depth,
    )


def create_result(
    task_id: str,
    agent_id: str,
    success: bool,
    output: Any,
    execution_time_ms: float = 0.0,
    metadata: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> AgentResult:
    """Helper function to create an AgentResult.

    Args:
        task_id: ID of the task
        agent_id: ID of the agent
        success: Whether task succeeded
        output: Task output
        execution_time_ms: Execution time
        metadata: Additional metadata
        error: Error message if failed

    Returns:
        New AgentResult instance
    """
    return AgentResult(
        task_id=task_id,
        agent_id=agent_id,
        success=success,
        output=output,
        execution_time_ms=execution_time_ms,
        metadata=metadata or {},
        error=error,
    )
