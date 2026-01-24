"""Agent - Resume modification agent using Google GenAI SDK."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from pathlib import Path

from .llm import GeminiAgent, LLMConfig, load_config
from .tools import (
    BaseTool,
    FileReadTool,
    FileWriteTool,
    FileListTool,
    BashTool,
    ResumeParserTool,
    ResumeWriterTool,
)
from .skills import RESUME_EXPERT_PROMPT


@dataclass
class AgentConfig:
    """Agent configuration."""
    workspace_dir: str = "."
    max_steps: int = 50
    system_prompt: str = RESUME_EXPERT_PROMPT
    verbose: bool = True


class ResumeAgent:
    """Resume modification agent with tool-use capabilities via Google GenAI SDK."""

    def __init__(
        self,
        llm_config: Optional[LLMConfig] = None,
        agent_config: Optional[AgentConfig] = None,
    ):
        self.llm_config = llm_config or load_config()
        self.agent_config = agent_config or AgentConfig()
        
        # Initialize the Gemini agent with system prompt
        self.agent = GeminiAgent(
            config=self.llm_config,
            system_prompt=self.agent_config.system_prompt,
        )
        
        # Initialize and register tools
        self.tools = self._init_tools()
        self._register_tools()

    def _init_tools(self) -> dict:
        """Initialize available tools."""
        workspace = self.agent_config.workspace_dir
        
        return {
            "file_read": FileReadTool(workspace),
            "file_write": FileWriteTool(workspace),
            "file_list": FileListTool(workspace),
            "bash": BashTool(workspace),
            "resume_parse": ResumeParserTool(workspace),
            "resume_write": ResumeWriterTool(workspace),
        }

    def _register_tools(self):
        """Register tools with the Gemini agent."""
        for name, tool in self.tools.items():
            # Convert tool parameters to the format expected by register_tool
            params = {
                "properties": tool.parameters,
                "required": [k for k, v in tool.parameters.items() if v.get("required", False)],
            }
            
            self.agent.register_tool(
                name=tool.name,
                description=tool.description,
                parameters=params,
                func=tool.execute,
            )

    async def run(self, user_input: str) -> str:
        """Run the agent with user input and return final response."""
        if self.agent_config.verbose:
            print(f"\n👤 User: {user_input[:100]}{'...' if len(user_input) > 100 else ''}")
            print("\n🤔 Thinking...")
        
        response = await self.agent.run(
            user_input=user_input,
            max_steps=self.agent_config.max_steps,
        )
        
        if self.agent_config.verbose:
            print(f"\n🤖 Assistant: {response[:200]}{'...' if len(response) > 200 else ''}")
        
        return response

    async def chat(self, user_input: str) -> str:
        """Alias for run() - for interactive use."""
        return await self.run(user_input)

    def reset(self):
        """Reset conversation history."""
        self.agent.reset()


async def main():
    """Test the agent."""
    agent = ResumeAgent()
    
    response = await agent.run(
        "List all files in the current directory and tell me what you see."
    )
    print("\n" + "=" * 50)
    print("Final Response:")
    print(response)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
