"""OrchestratorAgent - Coordinates specialized agents for complex tasks."""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from .base import BaseAgent, AgentConfig
from .protocol import AgentTask, AgentResult, create_result
from ..skills.orchestrator_prompt import ORCHESTRATOR_AGENT_PROMPT

if TYPE_CHECKING:
    from ..llm import GeminiAgent
    from ..observability import AgentObserver
    from .delegation import DelegationManager
    from .registry import AgentRegistry


class OrchestratorAgent(BaseAgent):
    """Orchestrator agent that coordinates specialized agents.

    The orchestrator:
    - Receives user requests
    - Breaks complex tasks into subtasks
    - Delegates to appropriate specialized agents
    - Aggregates results into cohesive responses

    Capabilities:
    - task_route: Route tasks to appropriate agents
    - workflow_coordinate: Coordinate multi-step workflows
    - result_aggregate: Combine results from multiple agents

    Tools:
    - delegate_to_parser: Delegate to ParserAgent
    - delegate_to_writer: Delegate to WriterAgent
    - delegate_to_formatter: Delegate to FormatterAgent
    - file_list: List files in workspace
    - bash: Execute shell commands
    """

    def __init__(
        self,
        agent_id: str = "orchestrator_agent",
        config: Optional[AgentConfig] = None,
        llm_agent: Optional[GeminiAgent] = None,
        observer: Optional[AgentObserver] = None,
        registry: Optional[AgentRegistry] = None,
        delegation_manager: Optional[DelegationManager] = None,
    ):
        """Initialize the orchestrator agent.

        Args:
            agent_id: Unique identifier for this agent
            config: Agent configuration
            llm_agent: The underlying LLM agent
            observer: Observer for logging and metrics
            registry: Agent registry for finding specialized agents
            delegation_manager: Manager for handling delegations
        """
        # Default config with moderate temperature
        if config is None:
            config = AgentConfig(temperature=0.5, max_steps=30)

        super().__init__(
            agent_id=agent_id,
            agent_type="orchestrator",
            capabilities=["task_route", "workflow_coordinate", "result_aggregate"],
            config=config,
            llm_agent=llm_agent,
            observer=observer,
        )

        self.registry = registry
        self.delegation_manager = delegation_manager
        self.system_prompt = ORCHESTRATOR_AGENT_PROMPT
        self._agent_tools: List = []

    def set_registry(self, registry: AgentRegistry) -> None:
        """Set the agent registry.

        Args:
            registry: Agent registry to use
        """
        self.registry = registry

    def set_delegation_manager(self, delegation_manager: DelegationManager) -> None:
        """Set the delegation manager.

        Args:
            delegation_manager: Delegation manager to use
        """
        self.delegation_manager = delegation_manager

    def register_agent_tools(self) -> None:
        """Register specialized agents as tools.

        This method creates AgentTool wrappers for each specialized
        agent in the registry and registers them with the LLM agent.
        """
        if not self.registry or not self.delegation_manager or not self.llm_agent:
            return

        from .agent_tool import AgentTool

        # Get all non-orchestrator agents
        for agent in self.registry.get_all_agents():
            if agent.agent_type == "orchestrator":
                continue

            # Create AgentTool wrapper
            agent_tool = AgentTool(
                agent=agent,
                delegation_manager=self.delegation_manager,
                from_agent=self.agent_id,
            )

            # Register with LLM agent
            self.llm_agent.register_tool(
                name=agent_tool.name,
                description=agent_tool.description,
                parameters=agent_tool.get_parameters(),
                func=agent_tool.execute,
            )

            self._agent_tools.append(agent_tool)

    def can_handle(self, task: AgentTask) -> bool:
        """Check if this agent can handle the given task.

        The orchestrator can handle any task by delegating to
        specialized agents.

        Args:
            task: The task to check

        Returns:
            True (orchestrator can handle any task)
        """
        return True

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute a task by coordinating specialized agents.

        Args:
            task: The task to execute

        Returns:
            AgentResult with the coordinated outcome
        """
        if not self.llm_agent:
            return create_result(
                task_id=task.task_id,
                agent_id=self.agent_id,
                success=False,
                output="",
                error="LLM agent not initialized",
            )

        try:
            # Build the prompt for the LLM
            prompt = self._build_prompt(task)

            # Run the LLM agent (which will use agent tools for delegation)
            response = await self.llm_agent.run(
                user_input=prompt,
                max_steps=self.config.max_steps,
            )

            return create_result(
                task_id=task.task_id,
                agent_id=self.agent_id,
                success=True,
                output=response,
                metadata={
                    "task_type": task.task_type,
                    "parameters": task.parameters,
                    "delegations": self.stats.delegations_made,
                },
            )

        except Exception as e:
            return create_result(
                task_id=task.task_id,
                agent_id=self.agent_id,
                success=False,
                output="",
                error=str(e),
            )

    def _build_prompt(self, task: AgentTask) -> str:
        """Build the prompt for the LLM based on the task.

        Args:
            task: The task to build a prompt for

        Returns:
            Prompt string for the LLM
        """
        prompt_parts = [task.description]

        # Add parameters if present
        if task.parameters:
            prompt_parts.append(f"\nTask parameters: {task.parameters}")

        # Add context if present
        if task.context:
            prompt_parts.append(f"\nContext: {task.context}")

        return "\n".join(prompt_parts)

    async def run(self, user_input: str, max_steps: Optional[int] = None) -> str:
        """Run the orchestrator with user input.

        This is the main entry point for user interactions.

        Args:
            user_input: The user's request
            max_steps: Maximum steps to execute

        Returns:
            Response string
        """
        if not self.llm_agent:
            return "Error: LLM agent not initialized"

        # Ensure agent tools are registered
        if not self._agent_tools:
            self.register_agent_tools()

        return await self.llm_agent.run(
            user_input=user_input,
            max_steps=max_steps or self.config.max_steps,
        )

    def reset(self) -> None:
        """Reset the orchestrator state."""
        if self.llm_agent:
            self.llm_agent.reset()
        self.reset_stats()

        if self.delegation_manager:
            self.delegation_manager.clear_history()

    def get_delegation_tree(self, task_id: str) -> str:
        """Get the delegation tree for a task.

        Args:
            task_id: ID of the root task

        Returns:
            ASCII representation of the delegation tree
        """
        if not self.delegation_manager:
            return "No delegation manager available"

        return self.delegation_manager.print_delegation_tree(task_id)

    def get_agent_stats(self) -> dict:
        """Get statistics for all agents.

        Returns:
            Dictionary with agent statistics
        """
        if not self.registry:
            return {}

        return self.registry.get_stats()
