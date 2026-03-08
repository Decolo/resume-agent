"""Tool factory - Creates tool instances for agents."""

from typing import Any, Dict, Optional

from resume_agent.tools import (
    BashTool,
    FileEditTool,
    FileListTool,
    FileReadTool,
    FileRenameTool,
    FileWriteTool,
    JobMatcherTool,
    JobSearchTool,
    ResumeLinterTool,
    ResumeParserTool,
    ResumeValidatorTool,
    ResumeWriterTool,
    WebFetchTool,
    WebReadTool,
)


def create_tools(workspace_dir: str, raw_config: Optional[Dict[str, Any]] = None) -> Dict:
    """Create all available tools for the agent.

    Args:
        workspace_dir: Working directory for file-based tools
        raw_config: Optional raw config dict (from config.yaml) for CDP settings

    Returns:
        Dictionary mapping tool names to tool instances
    """
    merged_config = raw_config or {}
    cdp = merged_config.get("cdp") or {}

    cdp_port = cdp.get("port", 0)
    chrome_profile = cdp.get("chrome_profile", "~/.resume-agent/chrome-profile")
    auto_launch = cdp.get("auto_launch", True)

    return {
        "file_read": FileReadTool(workspace_dir),
        "file_write": FileWriteTool(workspace_dir),
        "file_list": FileListTool(workspace_dir),
        "file_rename": FileRenameTool(workspace_dir),
        "file_edit": FileEditTool(workspace_dir),
        "bash": BashTool(workspace_dir),
        "resume_parse": ResumeParserTool(workspace_dir),
        "resume_write": ResumeWriterTool(workspace_dir),
        "lint_resume": ResumeLinterTool(workspace_dir),
        "job_match": JobMatcherTool(workspace_dir),
        "resume_validate": ResumeValidatorTool(workspace_dir),
        "job_search": JobSearchTool(
            cdp_port=cdp_port,
            chrome_profile=chrome_profile,
            auto_launch=auto_launch,
            api_key=merged_config.get("api_key", ""),
        ),
        "web_fetch": WebFetchTool(),
        "web_read": WebReadTool(),
    }
