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
    merged_config = raw_config or {}
    cdp = merged_config.get("cdp", {})
    linkedin = merged_config.get("linkedin", {})
    linkedin_cdp = linkedin.get("cdp", {})
    linkedin_patchright = linkedin.get("patchright", {})

    cdp_port = linkedin_cdp.get("port", cdp.get("port", 9222))
    chrome_profile = linkedin_cdp.get("chrome_profile", cdp.get("chrome_profile", "~/.resume-agent/chrome-profile"))
    auto_launch = linkedin_cdp.get("auto_launch", cdp.get("auto_launch", True))
    linkedin_driver = linkedin.get("driver", "cdp")
    patchright_headless = linkedin_patchright.get("headless", False)
    patchright_channel = linkedin_patchright.get("channel", "chrome")
    patchright_executable_path = linkedin_patchright.get("executable_path")
    patchright_cdp_endpoint = linkedin_patchright.get("cdp_endpoint")
    patchright_auto_launch = linkedin_patchright.get("auto_launch", auto_launch)
    effective_auto_launch = (
        patchright_auto_launch if str(linkedin_driver).lower() in {"patchright", "playwright"} else auto_launch
    )

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
        "job_search": JobSearchTool(
            cdp_port=cdp_port,
            chrome_profile=chrome_profile,
            auto_launch=effective_auto_launch,
            driver=linkedin_driver,
            patchright_headless=patchright_headless,
            patchright_channel=patchright_channel,
            patchright_executable_path=patchright_executable_path,
            patchright_cdp_endpoint=patchright_cdp_endpoint,
        ),
        "job_detail": JobDetailTool(
            cdp_port=cdp_port,
            chrome_profile=chrome_profile,
            auto_launch=effective_auto_launch,
            driver=linkedin_driver,
            patchright_headless=patchright_headless,
            patchright_channel=patchright_channel,
            patchright_executable_path=patchright_executable_path,
            patchright_cdp_endpoint=patchright_cdp_endpoint,
        ),
        "web_fetch": WebFetchTool(),
        "web_read": WebReadTool(),
    }
