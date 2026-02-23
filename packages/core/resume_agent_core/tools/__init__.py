"""Core tool abstractions -- BaseTool and ToolResult only.

Concrete tool implementations live in the tools packages:
- resume_agent_tools_cli  (file, bash, resume parse/write/validate/score/match)
- resume_agent_tools_web  (web fetch/read, section update, JD analysis)
"""

from .base import BaseTool, ToolResult

__all__ = [
    "BaseTool",
    "ToolResult",
]
