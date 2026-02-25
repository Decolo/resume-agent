"""Core tool abstractions -- BaseTool and ToolResult only.

Concrete tool implementations live in the tools package:
- resume_agent_tools_cli  (file, bash, web fetch/read, resume parse/write/validate/score/match)
"""

from .base import BaseTool, ToolResult

__all__ = [
    "BaseTool",
    "ToolResult",
]
