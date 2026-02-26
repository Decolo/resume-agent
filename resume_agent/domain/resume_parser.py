"""Pure domain logic for resume parsing and section extraction.

All functions operate on strings/dicts -- no file I/O.
File reading is the responsibility of the tools layer.
"""

from __future__ import annotations

import re
from typing import Dict, Tuple

# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------

#: Regex patterns mapping raw header text to canonical section names.
SECTION_PATTERNS: list[tuple[str, str]] = [
    (r"(?i)(summary|objective|profile|about)", "summary"),
    (r"(?i)(experience|work\s*history|employment)", "experience"),
    (r"(?i)(education|academic|qualification)", "education"),
    (r"(?i)(skills|technical\s*skills|competencies)", "skills"),
    (r"(?i)(projects|portfolio)", "projects"),
    (r"(?i)(certifications?|licenses?)", "certifications"),
    (r"(?i)(awards?|honors?|achievements?)", "awards"),
    (r"(?i)(publications?|papers?)", "publications"),
    (r"(?i)(languages?)", "languages"),
    (r"(?i)(references?)", "references"),
]


def extract_sections(content: str) -> Dict[str, str]:
    """Extract common resume sections from plain-text content.

    Returns a dict mapping canonical section names (e.g. ``"experience"``)
    to the text found under that heading.  Content before the first
    recognised heading is stored under ``"header"``.
    """
    sections: Dict[str, str] = {}
    lines = content.split("\n")
    current_section = "header"
    current_content: list[str] = []

    for line in lines:
        matched = False
        for pattern, section_name in SECTION_PATTERNS:
            if re.match(pattern, line.strip()):
                if current_content:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = section_name
                current_content = []
                matched = True
                break

        if not matched:
            current_content.append(line)

    if current_content:
        sections[current_section] = "\n".join(current_content).strip()

    return sections


# ---------------------------------------------------------------------------
# JSON Resume → readable text
# ---------------------------------------------------------------------------


def json_resume_to_text(data: dict) -> Tuple[str, dict]:
    """Convert a JSON Resume dict into human-readable text.

    Returns ``(text, metadata)`` where *metadata* contains
    ``{"format": "json_resume", "sections": [...]}``.
    """
    text_parts: list[str] = []

    if "basics" in data:
        basics = data["basics"]
        text_parts.append(f"# {basics.get('name', 'Unknown')}")
        text_parts.append(f"{basics.get('label', '')}")
        text_parts.append(f"Email: {basics.get('email', '')}")
        text_parts.append(f"Phone: {basics.get('phone', '')}")
        if "location" in basics:
            loc = basics["location"]
            text_parts.append(f"Location: {loc.get('city', '')}, {loc.get('region', '')}")
        text_parts.append(f"\n{basics.get('summary', '')}")

    if "work" in data:
        text_parts.append("\n## Work Experience")
        for job in data["work"]:
            text_parts.append(f"\n### {job.get('position', '')} at {job.get('company', '')}")
            text_parts.append(f"{job.get('startDate', '')} - {job.get('endDate', 'Present')}")
            text_parts.append(job.get("summary", ""))
            for highlight in job.get("highlights", []):
                text_parts.append(f"- {highlight}")

    if "education" in data:
        text_parts.append("\n## Education")
        for edu in data["education"]:
            text_parts.append(f"\n### {edu.get('studyType', '')} in {edu.get('area', '')}")
            text_parts.append(f"{edu.get('institution', '')}")
            text_parts.append(f"{edu.get('startDate', '')} - {edu.get('endDate', '')}")

    if "skills" in data:
        text_parts.append("\n## Skills")
        for skill in data["skills"]:
            keywords = ", ".join(skill.get("keywords", []))
            text_parts.append(f"- {skill.get('name', '')}: {keywords}")

    metadata = {"format": "json_resume", "sections": list(data.keys())}
    return "\n".join(text_parts), metadata
