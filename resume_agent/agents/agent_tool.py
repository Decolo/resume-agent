"""AgentTool - Wraps agents as tools for delegation."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any, Dict, Optional

from ..tools.base import BaseTool, ToolResult
from .protocol import AgentTask, generate_task_id

if TYPE_CHECKING:
    from .base import BaseAgent
    from .delegation import DelegationManager


# Agents that require an input file path
FILE_BASED_AGENTS = {"parser"}


class AgentTool(BaseTool):
    """Wraps an agent as a tool that can be called by other agents.

    This enables the agent-as-tool pattern where the orchestrator
    can delegate tasks to specialized agents using the same
    function calling interface as regular tools.

    Example:
        parser_tool = AgentTool(
            agent=parser_agent,
            delegation_manager=delegation_manager,
            from_agent="orchestrator"
        )

        # Register with orchestrator's LLM agent
        orchestrator.llm_agent.register_tool(
            name=parser_tool.name,
            description=parser_tool.description,
            parameters=parser_tool.get_parameters(),
            func=parser_tool.execute
        )

        # Now orchestrator can call delegate_to_parser as a tool
    """

    def __init__(
        self,
        agent: BaseAgent,
        delegation_manager: DelegationManager,
        from_agent: str = "orchestrator",
    ):
        """Initialize the agent tool.

        Args:
            agent: The agent to wrap as a tool
            delegation_manager: Manager for handling delegation
            from_agent: ID of the agent that will use this tool
        """
        self.agent = agent
        self.delegation_manager = delegation_manager
        self.from_agent = from_agent

        # Set tool properties
        self.name = f"delegate_to_{agent.agent_type}"
        self.description = self._generate_description()
        self.parameters = self._generate_parameters()

    def _generate_description(self) -> str:
        """Generate tool description based on agent capabilities.

        Returns:
            Description string for the tool
        """
        capabilities = ", ".join(self.agent.capabilities)
        return (
            f"Delegate a task to the {self.agent.agent_type} agent. "
            f"This agent specializes in: {capabilities}. "
            f"Use this tool when you need to {self._get_capability_description()}."
        )

    def _get_capability_description(self) -> str:
        """Get human-readable description of agent capabilities.

        Returns:
            Description of what the agent can do
        """
        capability_descriptions = {
            "parser": "parse resumes, analyze content, or extract information",
            "writer": "improve content, generate text, or optimize for ATS",
            "formatter": "convert formats, generate output files, or validate formatting",
            "orchestrator": "coordinate complex multi-step tasks",
        }
        return capability_descriptions.get(
            self.agent.agent_type, "perform specialized tasks"
        )

    def _generate_parameters(self) -> Dict[str, Any]:
        """Generate tool parameters schema.

        Returns:
            Parameters dictionary in OpenAI format
        """
        params = {
            "task_description": {
                "type": "string",
                "description": "Clear description of the task to delegate",
                "required": True,
            },
        }

        # Add required path parameter for file-based agents
        if self.agent.agent_type in FILE_BASED_AGENTS:
            params["path"] = {
                "type": "string",
                "description": "Input resume file path (e.g., 'examples/resume.md'). REQUIRED.",
                "required": True,
            }
        elif self.agent.agent_type == "writer":
            params["path"] = {
                "type": "string",
                "description": "Input resume file path (optional). If provided, writer can read it.",
                "required": False,
            }
        elif self.agent.agent_type == "formatter":
            params["path"] = {
                "type": "string",
                "description": "Input resume file path (optional if content is provided).",
                "required": False,
            }

        # Optional parameters
        params["parameters"] = {
            "type": "object",
            "description": "Additional parameters for the task",
            "required": False,
        }
        params["context"] = {
            "type": "object",
            "description": "Context data to pass to the agent (e.g., parsed resume data from previous step)",
            "required": False,
        }

        return params

    def get_parameters(self) -> Dict[str, Any]:
        """Get parameters in the format expected by register_tool.

        Returns:
            Parameters dictionary with properties and required fields
        """
        return {
            "properties": self.parameters,
            "required": [
                k for k, v in self.parameters.items() if v.get("required", False)
            ],
        }

    async def execute(self, **kwargs) -> ToolResult:
        """Execute by delegating to the wrapped agent.

        Args:
            **kwargs: Keyword arguments including:
                - task_description: Description of the task to perform
                - path: File path (required for parser/formatter agents)
                - parameters: Task-specific parameters
                - context: Context data for the agent

        Returns:
            ToolResult with the delegation outcome
        """
        task_description = kwargs.get("task_description", "")
        path = kwargs.get("path")
        raw_parameters = kwargs.get("parameters")
        raw_context = kwargs.get("context")

        def _normalize_payload(value: Any, fallback_key: Optional[str] = None) -> Dict[str, Any]:
            if isinstance(value, dict):
                return value
            if value is None:
                return {}
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, dict):
                        return parsed
                    if fallback_key:
                        return {fallback_key: parsed}
                    return {}
                except json.JSONDecodeError:
                    if fallback_key:
                        return {fallback_key: value}
                    return {}
            if fallback_key:
                return {fallback_key: value}
            return {}

        # Normalize parameter/context types (parse JSON strings when possible)
        parameters = _normalize_payload(raw_parameters, fallback_key="content")
        context = _normalize_payload(raw_context)

        # Promote path from parameters when LLM nests it there
        if not path and isinstance(parameters, dict) and "path" in parameters:
            path = parameters.pop("path")

        # Validate path for file-based agents
        if self.agent.agent_type in FILE_BASED_AGENTS:
            if not path:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"'path' parameter is required for {self.agent.agent_type} agent. "
                          f"Please specify the file path to the resume.",
                )

            # Check if file exists
            if not os.path.exists(path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File not found: {path}. Please check the path and try again.",
                )

            # Add path to parameters
            parameters["path"] = path
        elif self.agent.agent_type == "writer":
            if path:
                if not os.path.exists(path):
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"File not found: {path}. Please check the path and try again.",
                    )
                parameters["path"] = path

            # If parsed content is provided in context, pass it as content
            if not parameters.get("content"):
                parsed_resume = context.get("parsed_resume")
                if isinstance(parsed_resume, str) and parsed_resume.strip():
                    parameters["content"] = parsed_resume
        elif self.agent.agent_type == "formatter":
            # Formatter can accept either a file path or direct content
            if path:
                if not os.path.exists(path):
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"File not found: {path}. Please check the path and try again.",
                    )
                parameters["path"] = path
            elif not parameters.get("content"):
                return ToolResult(
                    success=False,
                    output="",
                    error="Formatter requires either 'path' to an input file or 'parameters.content'.",
                )

        # Create AgentTask
        task = AgentTask(
            task_id=generate_task_id(),
            task_type=self.agent.agent_type,
            description=task_description,
            parameters=parameters,
            context=context,
        )

        try:
            # Delegate to the agent
            result = await self.delegation_manager.delegate(
                task=task,
                from_agent=self.from_agent,
                to_agent=self.agent.agent_id,
            )

            return ToolResult(
                success=result.success,
                output=str(result.output),
                error=result.error,
                data={
                    "task_id": result.task_id,
                    "agent_id": result.agent_id,
                    "metadata": result.metadata,
                },
                execution_time_ms=result.execution_time_ms,
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Delegation failed: {str(e)}",
                data={"task_id": task.task_id, "agent_id": self.agent.agent_id},
            )

    def __repr__(self) -> str:
        return (
            f"AgentTool(name={self.name!r}, "
            f"agent={self.agent.agent_id!r}, "
            f"from_agent={self.from_agent!r})"
        )
