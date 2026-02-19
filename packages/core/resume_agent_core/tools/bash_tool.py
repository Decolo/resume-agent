"""Bash tool - execute shell commands."""

import asyncio
import os
import platform
from pathlib import Path

from .base import BaseTool, ToolResult


class BashTool(BaseTool):
    """Execute shell commands."""

    name = "bash"
    description = "Execute a shell command and return its output. Use for file operations, git commands, etc."
    parameters = {
        "command": {
            "type": "string",
            "description": "The shell command to execute",
            "required": True,
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds (default: 60)",
            "default": 60,
        },
    }

    # Commands that are not allowed for safety
    BLOCKED_COMMANDS = [
        # Destructive operations
        "rm",
        "rmdir",
        "del",
        "format",
        "dd",
        "mkfs",
        "fdisk",
        # System control
        "shutdown",
        "reboot",
        "halt",
        "poweroff",
        "kill",
        "killall",
        "pkill",
        # Permission changes
        "chmod",
        "chown",
        "chgrp",
        # Privilege escalation
        "sudo",
        "su",
        "doas",
        # Network access
        "curl",
        "wget",
        "nc",
        "netcat",
        # Fork bomb
        ":(){:|:&};:",
    ]

    # Dangerous patterns that indicate shell injection or command chaining
    DANGEROUS_PATTERNS = [
        ";",  # Command separator
        "&&",  # Logical AND
        "||",  # Logical OR
        "|",  # Pipe
        "`",  # Command substitution
        "$(",  # Command substitution
        "${",  # Variable expansion
        ">",  # Output redirection
        ">>",  # Append redirection
        "2>",  # Error redirection
        "<",  # Input redirection
    ]

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.is_windows = platform.system() == "Windows"

    def _is_safe_command(self, command: str) -> tuple[bool, str]:
        """
        Validate if a command is safe to execute.

        Returns:
            (is_safe, reason) tuple
        """
        # Check for blocked commands
        for blocked in self.BLOCKED_COMMANDS:
            if blocked in command.lower():
                return False, f"Command blocked for safety: contains '{blocked}'"

        # Check for dangerous patterns
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern in command:
                return False, f"Command blocked for safety: contains dangerous pattern '{pattern}'"

        return True, ""

    async def execute(self, command: str, timeout: int = 60) -> ToolResult:
        # Safety check
        is_safe, reason = self._is_safe_command(command)
        if not is_safe:
            return ToolResult(
                success=False,
                output="",
                error=reason,
            )

        try:
            if self.is_windows:
                shell_cmd = ["powershell", "-Command", command]
            else:
                shell_cmd = ["bash", "-c", command]

            process = await asyncio.create_subprocess_exec(
                *shell_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace_dir),
                env={**os.environ, "PATH": os.environ.get("PATH", "")},
            )

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Command timed out after {timeout} seconds",
                )

            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()

            if process.returncode == 0:
                output = stdout_str
                if stderr_str:
                    output += f"\n[stderr]: {stderr_str}"
                return ToolResult(
                    success=True,
                    output=output or "(no output)",
                    data={"exit_code": process.returncode},
                )
            else:
                return ToolResult(
                    success=False,
                    output=stdout_str,
                    error=stderr_str or f"Command failed with exit code {process.returncode}",
                    data={"exit_code": process.returncode},
                )

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
