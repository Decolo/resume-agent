"""Lightweight structured parser for resume markdown/plain text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List

EXPERIENCE_SECTION_KEYWORDS = {
    "experience",
    "professional experience",
    "work history",
    "employment",
    "工作经历",
    "工作经验",
}


@dataclass
class ResumeAst:
    """Structured content used by lint rules."""

    text: str
    lines: List[str]
    sections: Dict[str, List[str]]
    bullets_by_section: Dict[str, List[str]]

    @property
    def bullets(self) -> List[str]:
        merged: List[str] = []
        for values in self.bullets_by_section.values():
            merged.extend(values)
        return merged

    @property
    def has_experience_section(self) -> bool:
        return "experience" in self.sections

    def get_experience_bullets(self) -> List[str]:
        return list(self.bullets_by_section.get("experience", []))


def normalize_section_name(raw: str) -> str:
    """Normalize section heading to a stable key."""
    section = raw.strip().lower()
    section = re.sub(r"\s+", " ", section)
    if section in EXPERIENCE_SECTION_KEYWORDS:
        return "experience"
    return section


def parse_resume_ast(content: str) -> ResumeAst:
    """Parse text into section-aware structure with bullet extraction."""
    lines = [line.rstrip() for line in content.splitlines()]
    sections: Dict[str, List[str]] = {"root": []}
    bullets_by_section: Dict[str, List[str]] = {"root": []}
    current_section = "root"

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            sections[current_section].append("")
            continue

        heading = _extract_heading(line)
        if heading is not None:
            current_section = normalize_section_name(heading)
            sections.setdefault(current_section, [])
            bullets_by_section.setdefault(current_section, [])
            continue

        sections[current_section].append(raw_line)

        bullet = _extract_bullet_text(raw_line)
        if bullet:
            bullets_by_section.setdefault(current_section, []).append(bullet)

    return ResumeAst(
        text=content,
        lines=lines,
        sections=sections,
        bullets_by_section=bullets_by_section,
    )


def _extract_heading(line: str) -> str | None:
    if line.startswith("#"):
        value = re.sub(r"^#+\s*", "", line).strip()
        return value if value else None

    # Support plain uppercase style headings.
    if line.isupper() and len(line) > 3 and len(line.split()) <= 6:
        return line

    return None


def _extract_bullet_text(line: str) -> str | None:
    match = re.match(r"^\s*(?:[-*•]|\d+\.)\s+(.*)$", line)
    if not match:
        return None
    text = match.group(1).strip()
    return text or None
