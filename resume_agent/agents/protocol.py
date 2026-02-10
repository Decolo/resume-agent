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
