"""Pure domain logic for ATS (Applicant Tracking System) resume scoring.

All functions operate on content strings -- no file I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ATS_KEYWORDS: Dict[str, List[str]] = {
    "action_verbs": [
        "achieved",
        "administered",
        "analyzed",
        "built",
        "collaborated",
        "created",
        "delivered",
        "designed",
        "developed",
        "directed",
        "established",
        "executed",
        "generated",
        "implemented",
        "improved",
        "increased",
        "launched",
        "led",
        "managed",
        "optimized",
        "organized",
        "produced",
        "reduced",
        "resolved",
        "streamlined",
    ],
    "sections": [
        "experience",
        "education",
        "skills",
        "summary",
        "objective",
        "projects",
        "certifications",
        "awards",
        "achievements",
        "work history",
        "employment",
        "qualifications",
    ],
    "contact": ["email", "phone", "linkedin", "github", "portfolio"],
}

SCORING_WEIGHTS: Dict[str, float] = {
    "formatting": 0.20,
    "completeness": 0.25,
    "keywords": 0.30,
    "structure": 0.25,
}


@dataclass
class ATSScoreResult:
    """Structured result from ATS scoring."""

    overall_score: int
    formatting: Tuple[int, List[str]]
    completeness: Tuple[int, List[str]]
    keywords: Tuple[int, List[str]]
    structure: Tuple[int, List[str]]
    suggestions: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_ats(content: str, job_description: str = "") -> ATSScoreResult:
    """Score resume *content* for ATS compatibility.

    Returns an :class:`ATSScoreResult` with per-category breakdowns.
    Optionally accepts *job_description* for keyword matching.
    """
    fmt_score, fmt_issues = _check_formatting(content)
    comp_score, comp_issues = _check_completeness(content)
    kw_score, kw_issues = _check_keywords(content, job_description)
    struct_score, struct_issues = _check_structure(content)

    overall = round(
        fmt_score * SCORING_WEIGHTS["formatting"]
        + comp_score * SCORING_WEIGHTS["completeness"]
        + kw_score * SCORING_WEIGHTS["keywords"]
        + struct_score * SCORING_WEIGHTS["structure"]
    )

    suggestions: List[str] = []
    for issues in [fmt_issues, comp_issues, kw_issues, struct_issues]:
        suggestions.extend(issues)

    return ATSScoreResult(
        overall_score=overall,
        formatting=(fmt_score, fmt_issues),
        completeness=(comp_score, comp_issues),
        keywords=(kw_score, kw_issues),
        structure=(struct_score, struct_issues),
        suggestions=suggestions,
    )


# ---------------------------------------------------------------------------
# Formatting report (pure string output)
# ---------------------------------------------------------------------------


def format_ats_report(result: ATSScoreResult) -> str:
    """Render an :class:`ATSScoreResult` as a human-readable report."""
    grade = _score_to_grade(result.overall_score)
    bar = _score_bar(result.overall_score)

    fmt_score = result.formatting[0]
    comp_score = result.completeness[0]
    kw_score = result.keywords[0]
    struct_score = result.structure[0]

    lines = [
        f"## ATS Score: {result.overall_score}/100 {grade}",
        bar,
        "",
        "| Category     | Score | Weight |",
        "|-------------|-------|--------|",
        f"| Formatting   | {fmt_score:3d}   | {SCORING_WEIGHTS['formatting']:.0%}  |",
        f"| Completeness | {comp_score:3d}   | {SCORING_WEIGHTS['completeness']:.0%}  |",
        f"| Keywords     | {kw_score:3d}   | {SCORING_WEIGHTS['keywords']:.0%}  |",
        f"| Structure    | {struct_score:3d}   | {SCORING_WEIGHTS['structure']:.0%}  |",
    ]

    if result.suggestions:
        lines.append("")
        lines.append("### Suggestions")
        for i, s in enumerate(result.suggestions, 1):
            lines.append(f"{i}. {s}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Private scoring helpers
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "the",
    "and",
    "for",
    "are",
    "but",
    "not",
    "you",
    "all",
    "can",
    "had",
    "her",
    "was",
    "one",
    "our",
    "out",
    "has",
    "have",
    "been",
    "will",
    "with",
    "this",
    "that",
    "from",
    "they",
    "were",
    "which",
    "their",
    "about",
    "would",
    "there",
    "what",
    "also",
    "into",
    "more",
    "other",
}


def _check_formatting(content: str) -> Tuple[int, List[str]]:
    score = 100
    issues: List[str] = []

    if re.search(r"\|.*\|.*\|", content):
        score -= 15
        issues.append("Contains tables -- many ATS systems can't parse table layouts")

    fancy_chars = re.findall(r"[•●◆★☆►▸▹→←↑↓✓✗✔✘❌✅]", content)
    if fancy_chars:
        score -= 10
        issues.append(
            f"Contains special characters ({', '.join(sorted(set(fancy_chars))[:5])}) -- use standard bullets (- or *)"
        )

    long_lines = [line for line in content.split("\n") if len(line) > 120]
    if len(long_lines) > 5:
        score -= 10
        issues.append(f"{len(long_lines)} lines exceed 120 characters -- consider shorter lines for readability")

    if re.search(r"!\[.*?\]\(.*?\)", content):
        score -= 15
        issues.append("Contains embedded images -- ATS cannot read images")

    if re.search(r"\n{4,}", content):
        score -= 5
        issues.append("Excessive blank lines -- tighten spacing for cleaner formatting")

    return max(0, score), issues


def _check_completeness(content: str) -> Tuple[int, List[str]]:
    score = 100
    issues: List[str] = []
    content_lower = content.lower()

    has_email = bool(re.search(r"[\w\.\-+]+@[\w\.\-]+\.\w+", content))
    has_phone = bool(re.search(r"[\+]?[\d\-\(\)\s]{10,}", content))
    has_linkedin = "linkedin" in content_lower

    if not has_email:
        score -= 15
        issues.append("Missing email address -- essential for recruiter contact")
    if not has_phone:
        score -= 10
        issues.append("Missing phone number -- most recruiters expect a phone number")
    if not has_linkedin:
        score -= 5
        issues.append("No LinkedIn URL -- consider adding your LinkedIn profile")

    required_sections = {
        "experience": ["experience", "work history", "employment", "professional experience"],
        "education": ["education", "academic"],
        "skills": ["skills", "technical skills", "core competencies"],
    }
    optional_sections = {
        "summary": ["summary", "objective", "profile", "about me"],
        "projects": ["projects", "portfolio"],
    }

    for section_name, keywords in required_sections.items():
        if not any(kw in content_lower for kw in keywords):
            score -= 15
            issues.append(f"Missing '{section_name}' section -- this is expected by most ATS systems")

    for section_name, keywords in optional_sections.items():
        if not any(kw in content_lower for kw in keywords):
            score -= 5
            issues.append(f"No '{section_name}' section -- recommended for a complete resume")

    date_patterns = re.findall(
        r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*[\s,]+\d{4}|\d{4}\s*[-–—]\s*(?:\d{4}|present|current))",
        content_lower,
    )
    if not date_patterns:
        score -= 10
        issues.append("No dates found -- include employment dates (e.g., 'Jan 2020 - Present')")

    return max(0, score), issues


def _check_keywords(content: str, job_description: str = "") -> Tuple[int, List[str]]:
    score = 100
    issues: List[str] = []
    content_lower = content.lower()
    words = re.findall(r"\b[a-z]+\b", content_lower)

    found_verbs = [v for v in ATS_KEYWORDS["action_verbs"] if v in content_lower]
    verb_ratio = len(found_verbs) / max(len(ATS_KEYWORDS["action_verbs"]), 1)
    if verb_ratio < 0.2:
        score -= 20
        issues.append("Few action verbs found -- use strong verbs like: Led, Developed, Implemented, Achieved")
    elif verb_ratio < 0.4:
        score -= 10
        issues.append("Could use more action verbs -- try: Optimized, Streamlined, Delivered, Launched")

    numbers = re.findall(r"\d+[%$kKmMbB]|\$[\d,]+|\d+\+?\s*(?:years?|months?|clients?|users?|projects?)", content)
    if not numbers:
        score -= 20
        issues.append("No quantifiable achievements -- add metrics (e.g., 'Increased revenue by 25%')")
    elif len(numbers) < 3:
        score -= 10
        issues.append(f"Only {len(numbers)} metric(s) found -- aim for at least 3-5 quantified achievements")

    if job_description.strip():
        jd_lower = job_description.lower()
        jd_words = set(re.findall(r"\b[a-z]{3,}\b", jd_lower))
        jd_keywords = jd_words - _STOP_WORDS
        resume_words = set(words)

        matched = jd_keywords & resume_words
        missing = jd_keywords - resume_words

        match_rate = len(matched) / max(len(jd_keywords), 1)
        if match_rate < 0.3:
            score -= 25
            top_missing = sorted(missing)[:10]
            issues.append(f"Low job keyword match ({match_rate:.0%}) -- consider adding: {', '.join(top_missing)}")
        elif match_rate < 0.5:
            score -= 15
            top_missing = sorted(missing)[:7]
            issues.append(f"Moderate job keyword match ({match_rate:.0%}) -- missing: {', '.join(top_missing)}")

    return max(0, score), issues


def _check_structure(content: str) -> Tuple[int, List[str]]:
    score = 100
    issues: List[str] = []
    lines = content.split("\n")

    headers = [line for line in lines if re.match(r"^#{1,3}\s+\S", line) or (line.isupper() and len(line.strip()) > 3)]
    if len(headers) < 3:
        score -= 15
        issues.append("Few section headers found -- use clear headers (## Experience, ## Education, etc.)")

    bullet_styles: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            bullet_styles.add("-")
        elif stripped.startswith("* "):
            bullet_styles.add("*")
        elif re.match(r"^\d+\.\s", stripped):
            bullet_styles.add("numbered")
        elif stripped.startswith("• "):
            bullet_styles.add("•")

    if len(bullet_styles) > 1:
        score -= 10
        issues.append(f"Inconsistent bullet styles ({', '.join(bullet_styles)}) -- pick one style throughout")

    word_count = len(content.split())
    if word_count < 150:
        score -= 15
        issues.append(f"Resume is very short ({word_count} words) -- most resumes should be 300-800 words")
    elif word_count > 1200:
        score -= 10
        issues.append(f"Resume is long ({word_count} words) -- consider trimming to 1-2 pages (300-800 words)")

    date_formats: set[str] = set()
    if re.search(r"\b\d{1,2}/\d{4}\b", content):
        date_formats.add("MM/YYYY")
    if re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}\b", content):
        date_formats.add("Month YYYY")
    if re.search(r"\b\d{4}-\d{2}\b", content):
        date_formats.add("YYYY-MM")
    if len(date_formats) > 1:
        score -= 5
        issues.append(f"Mixed date formats ({', '.join(date_formats)}) -- use one consistent format")

    return max(0, score), issues


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _score_to_grade(score: int) -> str:
    if score >= 90:
        return "Excellent"
    elif score >= 75:
        return "Good"
    elif score >= 60:
        return "Fair"
    else:
        return "Needs Work"


def _score_bar(score: int, width: int = 20) -> str:
    filled = round(score / 100 * width)
    return f"[{'=' * filled}{' ' * (width - filled)}]"
