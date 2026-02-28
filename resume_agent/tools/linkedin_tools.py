"""LinkedIn job search tools — BaseTool subclasses using CDP for browser automation.

These tools connect to a Chrome instance via CDP to navigate LinkedIn
and extract job data as plain text, then use domain functions to parse
the text into structured results.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from resume_agent.core.tools.base import BaseTool, ToolResult
from resume_agent.domain.linkedin_jobs import (
    JobListing,
    build_detail_url,
    build_search_url,
    check_login_required,
    format_job_detail,
    format_job_listings,
    parse_job_detail,
    parse_job_listings,
)
from resume_agent.tools.cdp_client import CDPClient

logger = logging.getLogger(__name__)

_DEFAULT_CDP_PORT = 9222
_DEFAULT_CHROME_PROFILE = "~/.resume-agent/chrome-profile"
_LOGIN_CHECK_URL = "https://www.linkedin.com/feed/"
_LOGIN_ERROR = "LinkedIn login required. Please open the Chrome window, " "log into LinkedIn, then try again."
_PAGE_SIZE = 25  # LinkedIn results per page


async def _preflight_login_check(client: CDPClient) -> bool:
    """Navigate to LinkedIn feed and return True if login is required."""
    await client.navigate(_LOGIN_CHECK_URL)
    text = await client.extract_main_text()
    return check_login_required(text)


class JobSearchTool(BaseTool):
    """Search LinkedIn jobs by keywords and location."""

    name = "job_search"
    description = (
        "Search LinkedIn for job listings by keywords and optional location. "
        "Supports country/region-level locations (e.g. 'China', 'United States'). "
        "Automatically paginates to collect the requested number of results. "
        "Returns a compact list with title, company, location, and URL."
    )
    parameters: Dict[str, Any] = {
        "keywords": {
            "type": "string",
            "description": "Job search keywords (e.g. 'Senior Software Engineer')",
            "required": True,
        },
        "location": {
            "type": "string",
            "description": "Location filter (e.g. 'San Francisco, CA')",
        },
        "limit": {
            "type": "integer",
            "description": "Number of results to return. Automatically paginates if > 25. Default 25.",
            "default": 25,
        },
    }

    def __init__(
        self,
        cdp_port: int = _DEFAULT_CDP_PORT,
        chrome_profile: str = _DEFAULT_CHROME_PROFILE,
        auto_launch: bool = True,
    ):
        self.cdp_port = cdp_port
        self.chrome_profile = chrome_profile
        self.auto_launch = auto_launch

    async def execute(self, keywords: str = "", location: str = "", limit: int = 25) -> ToolResult:
        if not keywords or not keywords.strip():
            return ToolResult(success=False, output="", error="Missing required parameter: keywords")

        client = CDPClient(port=self.cdp_port, chrome_profile=self.chrome_profile, auto_launch=self.auto_launch)

        try:
            await client.connect()

            if await _preflight_login_check(client):
                return ToolResult(success=False, output="", error=_LOGIN_ERROR)

            all_jobs: List[JobListing] = []
            pages_needed = (limit + _PAGE_SIZE - 1) // _PAGE_SIZE  # ceil division

            for page in range(pages_needed):
                if len(all_jobs) >= limit:
                    break

                url = build_search_url(keywords.strip(), location.strip(), start=page * _PAGE_SIZE)
                await client.navigate(url)

                # Scroll to trigger lazy loading
                for _ in range(3):
                    await client.evaluate("window.scrollBy(0, window.innerHeight)")
                    import asyncio

                    await asyncio.sleep(1.5)
                await client.evaluate("window.scrollTo(0, 0)")

                text = await client.extract_main_text()
                page_jobs = parse_job_listings(text)

                if not page_jobs:
                    break  # no more results

                all_jobs.extend(page_jobs)

            all_jobs = all_jobs[:limit]

            output = format_job_listings(all_jobs)
            return ToolResult(
                success=True,
                output=output,
                data={
                    "jobs": [
                        {
                            "title": j.title,
                            "company": j.company,
                            "location": j.location,
                            "job_id": j.job_id,
                            "url": j.url,
                            "posted_time": j.posted_time,
                        }
                        for j in all_jobs
                    ],
                    "total": len(all_jobs),
                },
            )
        except ConnectionError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Cannot connect to Chrome: {e}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Job search failed: {e}")
        finally:
            await client.close()


class JobDetailTool(BaseTool):
    """Get full details of a LinkedIn job posting."""

    name = "job_detail"
    description = (
        "Get full details of a LinkedIn job posting by job ID. "
        "Returns title, company, location, full description, and metadata."
    )
    parameters: Dict[str, Any] = {
        "job_id": {
            "type": "string",
            "description": "LinkedIn job ID (numeric string from the job URL)",
            "required": True,
        },
    }

    def __init__(
        self,
        cdp_port: int = _DEFAULT_CDP_PORT,
        chrome_profile: str = _DEFAULT_CHROME_PROFILE,
        auto_launch: bool = True,
    ):
        self.cdp_port = cdp_port
        self.chrome_profile = chrome_profile
        self.auto_launch = auto_launch

    async def execute(self, job_id: str = "") -> ToolResult:
        if not job_id or not job_id.strip():
            return ToolResult(success=False, output="", error="Missing required parameter: job_id")

        client = CDPClient(port=self.cdp_port, chrome_profile=self.chrome_profile, auto_launch=self.auto_launch)

        try:
            await client.connect()

            if await _preflight_login_check(client):
                return ToolResult(success=False, output="", error=_LOGIN_ERROR)

            url = build_detail_url(job_id.strip())
            await client.navigate(url)
            text = await client.extract_main_text()
            detail = parse_job_detail(text)
            detail.url = url

            output = format_job_detail(detail)
            return ToolResult(
                success=True,
                output=output,
                data={
                    "title": detail.title,
                    "company": detail.company,
                    "location": detail.location,
                    "description": detail.description,
                    "url": detail.url,
                    "posted_time": detail.posted_time,
                    "seniority_level": detail.seniority_level,
                    "employment_type": detail.employment_type,
                },
            )
        except ConnectionError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Cannot connect to Chrome: {e}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Job detail fetch failed: {e}")
        finally:
            await client.close()
