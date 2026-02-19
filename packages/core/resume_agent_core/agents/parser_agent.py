"""ParserAgent - Specialized agent for resume parsing and analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ..skills.parser_prompt import PARSER_AGENT_PROMPT
from .base import AgentConfig, BaseAgent
from .protocol import AgentResult, AgentTask, create_result

if TYPE_CHECKING:
    from ..llm import LLMAgent
    from ..observability import AgentObserver


class ParserAgent(BaseAgent):
    """Specialized agent for resume parsing and analysis.

    Capabilities:
    - resume_parse: Parse resumes from various formats
    - resume_analyze: Analyze resume structure and content
    - resume_extract: Extract specific information from resumes

    Tools:
    - resume_parse: Parse PDF/DOCX/MD/JSON/TXT resumes
    - file_read: Read file contents
    - file_list: List files in workspace
    """

    def __init__(
        self,
        agent_id: str = "parser_agent",
        config: Optional[AgentConfig] = None,
        llm_agent: Optional[LLMAgent] = None,
        observer: Optional[AgentObserver] = None,
    ):
        """Initialize the parser agent.

        Args:
            agent_id: Unique identifier for this agent
            config: Agent configuration
            llm_agent: The underlying LLM agent
            observer: Observer for logging and metrics
        """
        # Default config with lower temperature for deterministic parsing
        if config is None:
            config = AgentConfig(temperature=0.3)

        super().__init__(
            agent_id=agent_id,
            agent_type="parser",
            capabilities=["resume_parse", "resume_analyze", "resume_extract"],
            config=config,
            llm_agent=llm_agent,
            observer=observer,
        )

        self.system_prompt = PARSER_AGENT_PROMPT

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

        # Check for parsing-related keywords in description
        parsing_keywords = [
            "parse",
            "read",
            "extract",
            "analyze",
            "structure",
            "content",
            "section",
        ]
        description_lower = task.description.lower()

        return any(keyword in description_lower for keyword in parsing_keywords)

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute a parsing or analysis task.

        Args:
            task: The task to execute

        Returns:
            AgentResult with the parsing outcome
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
            if "path" in task.parameters:
                prompt_parts.append(f"\nFile path: {task.parameters['path']}")
            if "format" in task.parameters:
                prompt_parts.append(f"\nExpected format: {task.parameters['format']}")

        # Add context if present
        if task.context:
            if "workspace" in task.context:
                prompt_parts.append(f"\nWorkspace: {task.context['workspace']}")

        return "\n".join(prompt_parts)
