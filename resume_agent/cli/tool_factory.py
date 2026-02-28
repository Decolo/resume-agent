"""Tool factory - Creates tool instances for agents."""

from typing import Any, Dict, Optional

from resume_agent.tools import (
    BashTool,
    FileListTool,
    FileReadTool,
    FileRenameTool,
    FileWriteTool,
    JobDetailTool,
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
    cdp = (raw_config or {}).get("cdp", {})
    cdp_port = cdp.get("port", 9222)
    chrome_profile = cdp.get("chrome_profile", "~/.resume-agent/chrome-profile")
    auto_launch = cdp.get("auto_launch", True)

    return {
        "file_read": FileReadTool(workspace_dir),
        "file_write": FileWriteTool(workspace_dir),
        "file_list": FileListTool(workspace_dir),
        "file_rename": FileRenameTool(workspace_dir),
        "bash": BashTool(workspace_dir),
        "resume_parse": ResumeParserTool(workspace_dir),
        "resume_write": ResumeWriterTool(workspace_dir),
        "lint_resume": ResumeLinterTool(workspace_dir),
        "job_match": JobMatcherTool(workspace_dir),
        "resume_validate": ResumeValidatorTool(workspace_dir),
        "job_search": JobSearchTool(cdp_port=cdp_port, chrome_profile=chrome_profile, auto_launch=auto_launch),
        "job_detail": JobDetailTool(cdp_port=cdp_port, chrome_profile=chrome_profile, auto_launch=auto_launch),
        "web_fetch": WebFetchTool(),
        "web_read": WebReadTool(),
    }
