"""Pure domain logic for LinkedIn job search — parse text, format output.

All functions operate on plain text strings (innerText from CDP).
No I/O, no network calls. This is the system boundary for testing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List
from urllib.parse import quote_plus


@dataclass
class JobListing:
    """A single job from a LinkedIn search results page."""

    title: str
    company: str
    location: str
    job_id: str = ""
    url: str = ""
    posted_time: str = ""


@dataclass
class JobDetail:
    """Full details of a single LinkedIn job posting."""

    title: str
    company: str
    location: str
    description: str
    url: str = ""
    posted_time: str = ""
    seniority_level: str = ""
    employment_type: str = ""


def parse_job_listings(text: str) -> List[JobListing]:
    """Parse LinkedIn search page innerText into structured job listings.

    LinkedIn's search page innerText follows a repeating pattern:
      Title
      Company
      Location
      Time posted / metadata
    separated by blank lines.
    """
    if not text or not text.strip():
        return []

    jobs: List[JobListing] = []
    # Split into blocks separated by blank lines
    blocks = re.split(r"\n\s*\n", text.strip())

    for block in blocks:
        lines = [line.strip() for line in block.strip().splitlines() if line.strip()]
        if len(lines) < 3:
            continue

        # Heuristic: skip navigation/header blocks
        if _is_noise_block(lines):
            continue

        title = lines[0]
        company = lines[1]
        location = lines[2]
        posted_time = lines[3] if len(lines) > 3 else ""

        jobs.append(
            JobListing(
                title=title,
                company=company,
                location=location,
                posted_time=posted_time,
            )
        )

    return jobs


def _is_noise_block(lines: List[str]) -> bool:
    """Filter out non-job blocks (nav, headers, footers)."""
    first = lines[0].lower()
    noise_starts = ["jobs", "search", "filter", "sort", "show", "page", "sign in", "log in"]
    if first in noise_starts:
        return True
    # Single-word first line that looks like a nav item
    if len(lines[0].split()) == 1 and len(lines) <= 2:
        return True
    return False


# ---------------------------------------------------------------------------
# Login detection
# ---------------------------------------------------------------------------

_LOGIN_SIGNALS = [
    "sign in",
    "sign up",
    "join now",
    "join linkedin",
    "log in",
    "forgot password",
    "new to linkedin",
    "sign in to view",
]


def check_login_required(text: str) -> bool:
    """Detect whether the page text indicates a LinkedIn login/authwall page."""
    if not text:
        return False
    lower = text[:2000].lower()  # only check the top of the page
    matches = sum(1 for signal in _LOGIN_SIGNALS if signal in lower)
    return matches >= 2


# ---------------------------------------------------------------------------
# Job detail parsing
# ---------------------------------------------------------------------------

_METADATA_LABELS = {
    "seniority level",
    "employment type",
    "job function",
    "industries",
}


def parse_job_detail(text: str) -> JobDetail:
    """Parse LinkedIn job detail page innerText into a JobDetail.

    The detail page typically has:
      Title
      Company
      Location
      (blank)
      About the job
      ... description paragraphs ...
      (blank)
      Seniority level / Employment type / etc.
    """
    lines = text.strip().splitlines()
    if len(lines) < 3:
        return JobDetail(title="", company="", location="", description=text.strip())

    title = lines[0].strip()
    company = lines[1].strip()
    location = lines[2].strip()

    # Collect description: everything between header and metadata sections
    desc_lines: List[str] = []
    seniority_level = ""
    employment_type = ""
    posted_time = ""
    in_description = False
    skip_next = False

    for i, line in enumerate(lines[3:], start=3):
        stripped = line.strip()
        lower = stripped.lower()

        if skip_next:
            # This line is the value for a metadata label
            if lower == "seniority level":
                pass  # handled below
            skip_next = False
            continue

        if lower in _METADATA_LABELS:
            # Next line is the value
            if i + 1 < len(lines):
                value = lines[i + 1].strip()
                if lower == "seniority level":
                    seniority_level = value
                elif lower == "employment type":
                    employment_type = value
            skip_next = True
            in_description = False
            continue

        if lower.startswith("posted") and ("ago" in lower or "applicant" in lower):
            posted_time = stripped
            continue

        if lower == "about the job":
            in_description = True
            continue

        if in_description or (not seniority_level and i > 3 and stripped):
            desc_lines.append(stripped)
            in_description = True

    description = "\n".join(desc_lines).strip()

    return JobDetail(
        title=title,
        company=company,
        location=location,
        description=description,
        seniority_level=seniority_level,
        employment_type=employment_type,
        posted_time=posted_time,
    )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_job_listings(jobs: List[JobListing]) -> str:
    """Format job listings into a compact report: title, company, location, url."""
    if not jobs:
        return "No job listings found."

    parts: List[str] = [f"Found {len(jobs)} job(s):\n"]
    for i, job in enumerate(jobs, 1):
        entry = f"{i}. {job.title}\n   {job.company} — {job.location}"
        if job.url:
            entry += f"\n   {job.url}"
        parts.append(entry)

    return "\n\n".join(parts)


def format_job_detail(job: JobDetail) -> str:
    """Format a job detail into a human-readable report."""
    parts = [
        f"{job.title}",
        f"{job.company} — {job.location}",
    ]
    if job.seniority_level:
        parts.append(f"Level: {job.seniority_level}")
    if job.employment_type:
        parts.append(f"Type: {job.employment_type}")
    if job.posted_time:
        parts.append(f"Posted: {job.posted_time}")
    parts.append("")
    parts.append(job.description)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------


def build_search_url(keywords: str, location: str = "", start: int = 0) -> str:
    """Build a LinkedIn job search URL."""
    params = f"keywords={quote_plus(keywords)}"
    if location:
        params += f"&location={quote_plus(location)}"
    if start > 0:
        params += f"&start={start}"
    return f"https://www.linkedin.com/jobs/search/?{params}"


def build_detail_url(job_id: str) -> str:
    """Build a LinkedIn job detail URL."""
    return f"https://www.linkedin.com/jobs/view/{job_id}/"
