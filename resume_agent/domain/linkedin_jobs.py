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


# ---------------------------------------------------------------------------
# URL builder
# ---------------------------------------------------------------------------


def build_search_url(keywords: str, location: str = "", start: int = 0) -> str:
    """Build a LinkedIn job search URL."""
    params = f"keywords={quote_plus(keywords)}"
    if location:
        params += f"&location={quote_plus(location)}"
    if start > 0:
        params += f"&start={start}"
    return f"https://www.linkedin.com/jobs/search/?{params}"
