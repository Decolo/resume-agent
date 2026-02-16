"""FormatterAgent - Specialized agent for resume formatting and conversion."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ..skills.formatter_prompt import FORMATTER_AGENT_PROMPT
from .base import AgentConfig, BaseAgent
from .protocol import AgentResult, AgentTask, create_result

if TYPE_CHECKING:
    from ..llm import LLMAgent
    from ..observability import AgentObserver


class FormatterAgent(BaseAgent):
    """Specialized agent for resume formatting and conversion.

    Capabilities:
    - format_convert: Convert resumes between formats
    - format_validate: Validate formatting compliance
    - format_optimize: Optimize layout and structure

    Tools:
    - resume_write: Generate output in various formats
    - file_read: Read source content
    - file_write: Save formatted output
    """

    def __init__(
        self,
        agent_id: str = "formatter_agent",
        config: Optional[AgentConfig] = None,
        llm_agent: Optional[LLMAgent] = None,
        observer: Optional[AgentObserver] = None,
    ):
        """Initialize the formatter agent.

        Args:
            agent_id: Unique identifier for this agent
            config: Agent configuration
            llm_agent: The underlying LLM agent
            observer: Observer for logging and metrics
        """
        # Default config with lower temperature for consistent formatting
        if config is None:
            config = AgentConfig(temperature=0.3)

        super().__init__(
            agent_id=agent_id,
            agent_type="formatter",
            capabilities=["format_convert", "format_validate", "format_optimize"],
            config=config,
            llm_agent=llm_agent,
            observer=observer,
        )

        self.system_prompt = FORMATTER_AGENT_PROMPT

    def can_handle(self, task: AgentTask) -> bool:
        """Check if this agent can handle the given task.

        Args:
            task: The task to check

        Returns:
            True if this agent can handle the task
        """
        # Check task type
        if task.task_type in self.capabilities:
            return True

        # Check for formatting-related keywords in description
        formatting_keywords = [
            "format",
            "convert",
            "export",
            "save",
            "output",
            "html",
            "markdown",
            "json",
            "pdf",
            "template",
            "layout",
        ]
        description_lower = task.description.lower()

        return any(keyword in description_lower for keyword in formatting_keywords)

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute a formatting or conversion task.

        Args:
            task: The task to execute

        Returns:
            AgentResult with the formatting outcome
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

            # Run the LLM agent
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
            if "output_format" in task.parameters:
                prompt_parts.append(f"\nOutput format: {task.parameters['output_format']}")
            if "output_path" in task.parameters:
                prompt_parts.append(f"\nOutput path: {task.parameters['output_path']}")
            if "content" in task.parameters:
                prompt_parts.append(f"\nContent to format:\n{task.parameters['content']}")

        # Add context if present
        if task.context:
            if "improved_content" in task.context:
                prompt_parts.append("\nImproved content available in context")
            if "source_format" in task.context:
                prompt_parts.append(f"\nSource format: {task.context['source_format']}")

        return "\n".join(prompt_parts)
