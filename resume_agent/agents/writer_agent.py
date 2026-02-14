"""WriterAgent - Specialized agent for resume content generation and improvement."""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .base import BaseAgent, AgentConfig
from .protocol import AgentTask, AgentResult, create_result
from ..skills.writer_prompt import WRITER_AGENT_PROMPT

if TYPE_CHECKING:
    from ..llm import LLMAgent
    from ..observability import AgentObserver


class WriterAgent(BaseAgent):
    """Specialized agent for resume content generation and improvement.

    Capabilities:
    - content_improve: Enhance existing resume content
    - content_generate: Generate new sections or bullet points
    - content_tailor: Customize content for specific jobs
    - ats_optimize: Optimize content for ATS systems

    Tools:
    - file_read: Read existing content and job descriptions
    - file_write: Save improved content
    """

    def __init__(
        self,
        agent_id: str = "writer_agent",
        config: Optional[AgentConfig] = None,
        llm_agent: Optional[LLMAgent] = None,
        observer: Optional[AgentObserver] = None,
    ):
        """Initialize the writer agent.

        Args:
            agent_id: Unique identifier for this agent
            config: Agent configuration
            llm_agent: The underlying LLM agent
            observer: Observer for logging and metrics
        """
        # Default config with higher temperature for creative writing
        if config is None:
            config = AgentConfig(temperature=0.7)

        super().__init__(
            agent_id=agent_id,
            agent_type="writer",
            capabilities=["content_improve", "content_generate", "content_tailor", "ats_optimize"],
            config=config,
            llm_agent=llm_agent,
            observer=observer,
        )

        self.system_prompt = WRITER_AGENT_PROMPT

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

        # Check for writing-related keywords in description
        writing_keywords = [
            "improve",
            "enhance",
            "write",
            "rewrite",
            "generate",
            "create",
            "tailor",
            "customize",
            "optimize",
            "ats",
            "bullet",
            "achievement",
            "action verb",
        ]
        description_lower = task.description.lower()

        return any(keyword in description_lower for keyword in writing_keywords)

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute a writing or improvement task.

        Args:
            task: The task to execute

        Returns:
            AgentResult with the writing outcome
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
            if "content" in task.parameters:
                prompt_parts.append(f"\nContent to improve:\n{task.parameters['content']}")
            if "job_description" in task.parameters:
                prompt_parts.append(f"\nTarget job description:\n{task.parameters['job_description']}")
            if "section" in task.parameters:
                prompt_parts.append(f"\nSection to focus on: {task.parameters['section']}")

        # Add context if present
        if task.context:
            if "parsed_resume" in task.context:
                prompt_parts.append(f"\nParsed resume data available in context")
            if "target_role" in task.context:
                prompt_parts.append(f"\nTarget role: {task.context['target_role']}")

        return "\n".join(prompt_parts)
