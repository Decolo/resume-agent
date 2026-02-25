"""Tool factory - Creates tool instances for agents."""

from typing import Dict

from resume_agent_tools_cli import (
    ATSScorerTool,
    BashTool,
    FileListTool,
    FileReadTool,
    FileRenameTool,
    FileWriteTool,
    JobMatcherTool,
    ResumeParserTool,
    ResumeValidatorTool,
    ResumeWriterTool,
    WebFetchTool,
    WebReadTool,
)


def create_tools(workspace_dir: str) -> Dict:
    """Create all available tools for the agent.

    Args:
        workspace_dir: Working directory for file-based tools

    Returns:
        Dictionary mapping tool names to tool instances
    """
    return {
        "file_read": FileReadTool(workspace_dir),
        "file_write": FileWriteTool(workspace_dir),
        "file_list": FileListTool(workspace_dir),
        "file_rename": FileRenameTool(workspace_dir),
        "bash": BashTool(workspace_dir),
        "resume_parse": ResumeParserTool(workspace_dir),
        "resume_write": ResumeWriterTool(workspace_dir),
        "ats_score": ATSScorerTool(workspace_dir),
        "job_match": JobMatcherTool(workspace_dir),
        "resume_validate": ResumeValidatorTool(workspace_dir),
        "web_fetch": WebFetchTool(),
        "web_read": WebReadTool(),
    }
