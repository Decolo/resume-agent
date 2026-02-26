"""Pure domain logic for job description matching against resumes.

All functions operate on content strings -- no file I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Set

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STOP_WORDS: Set[str] = {
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
    "than",
    "then",
    "them",
    "these",
    "some",
    "such",
    "only",
    "over",
    "very",
    "just",
    "being",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "between",
    "under",
    "again",
    "further",
    "once",
    "here",
    "when",
    "where",
    "both",
    "each",
    "most",
    "same",
    "should",
    "could",
    "does",
    "doing",
    "while",
    "must",
    "work",
    "working",
    "looking",
    "seeking",
    "ability",
    "able",
    "including",
    "using",
    "strong",
    "excellent",
    "good",
    "great",
    "well",
    "team",
    "role",
    "position",
    "company",
    "join",
    "ideal",
    "candidate",
    "required",
    "preferred",
    "minimum",
    "years",
    "year",
    "experience",
}


@dataclass
class JobMatchResult:
    """Structured result from job matching."""

    match_score: int
    matched_keywords: Set[str]
    missing_keywords: Set[str]
    extra_keywords: Set[str]
    requirements: Dict[str, List[str]]
    suggestions: List[Dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def match_job(resume_content: str, job_description: str) -> JobMatchResult:
    """Compare *resume_content* against *job_description*.

    Returns a :class:`JobMatchResult` with keyword overlap, gaps, and
    actionable suggestions.
    """
    resume_kw = extract_keywords(resume_content)
    jd_kw = extract_keywords(job_description)
    requirements = extract_requirements(job_description)

    matched = resume_kw & jd_kw
    missing = jd_kw - resume_kw
    extra = resume_kw - jd_kw

    score = _calculate_match_score(resume_kw, jd_kw, requirements, resume_content)
    suggestions = _generate_suggestions(missing, requirements, resume_content)

    return JobMatchResult(
        match_score=score,
        matched_keywords=matched,
        missing_keywords=missing,
        extra_keywords=extra,
        requirements=requirements,
        suggestions=suggestions,
    )


def extract_keywords(text: str) -> Set[str]:
    """Extract meaningful keywords from *text*, filtering stop words."""
    words = set(re.findall(r"\b[a-z][a-z\+\#\.]{2,}\b", text.lower()))
    multi_word = set(
        m.lower()
        for m in re.findall(
            r"\b(?:machine learning|deep learning|data science|project management|"
            r"full stack|front end|back end|cloud computing|"
            r"continuous integration|continuous delivery|"
            r"natural language processing|computer vision)\b",
            text.lower(),
        )
    )
    words |= multi_word
    return words - _STOP_WORDS


def extract_requirements(jd: str) -> Dict[str, List[str]]:
    """Extract structured requirements from a job description string."""
    reqs: Dict[str, List[str]] = {
        "required_skills": [],
        "preferred_skills": [],
        "qualifications": [],
    }
    jd_lower = jd.lower()

    req_section = re.search(
        r"(?:required|must have|requirements?|qualifications?)[:\s]*\n((?:[-\u2022*]\s*.+\n?)+)",
        jd_lower,
    )
    if req_section:
        items = re.findall(r"[-\u2022*]\s*(.+)", req_section.group(1))
        reqs["required_skills"] = [i.strip() for i in items]

    pref_section = re.search(
        r"(?:preferred|nice to have|bonus|desired)[:\s]*\n((?:[-\u2022*]\s*.+\n?)+)",
        jd_lower,
    )
    if pref_section:
        items = re.findall(r"[-\u2022*]\s*(.+)", pref_section.group(1))
        reqs["preferred_skills"] = [i.strip() for i in items]

    edu_match = re.search(
        r"(?:bachelor|master|phd|degree|b\.?s\.?|m\.?s\.?|mba)[^.]*",
        jd_lower,
    )
    if edu_match:
        reqs["qualifications"].append(edu_match.group().strip())

    exp_match = re.search(r"(\d+)\+?\s*years?\s*(?:of\s+)?experience", jd_lower)
    if exp_match:
        reqs["qualifications"].append(f"{exp_match.group(1)}+ years experience")

    return reqs


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_match_report(result: JobMatchResult) -> str:
    """Render a :class:`JobMatchResult` as a human-readable report."""
    grade = _score_to_grade(result.match_score)
    lines = [f"## Job Match Score: {result.match_score}/100 {grade}", ""]

    if result.matched_keywords:
        top = sorted(result.matched_keywords)[:20]
        lines.append(f"### Matching Keywords ({len(result.matched_keywords)})")
        lines.append(", ".join(top))
        lines.append("")

    if result.missing_keywords:
        top = sorted(result.missing_keywords)[:20]
        lines.append(f"### Missing Keywords ({len(result.missing_keywords)})")
        lines.append(", ".join(top))
        lines.append("")

    if any(result.requirements.values()):
        lines.append("### Requirements Analysis")
        for category, items in result.requirements.items():
            if items:
                label = category.replace("_", " ").title()
                lines.append(f"\n{label}:")
                for item in items:
                    lines.append(f"- {item}")
        lines.append("")

    if result.suggestions:
        lines.append("### Suggestions")
        for i, s in enumerate(result.suggestions, 1):
            lines.append(f"{i}. [{s['section']}] {s['detail']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _calculate_match_score(
    resume_kw: Set[str],
    jd_kw: Set[str],
    requirements: Dict[str, List[str]],
    resume_content: str,
) -> int:
    if not jd_kw:
        return 50

    overlap = len(resume_kw & jd_kw) / max(len(jd_kw), 1)
    kw_score = min(overlap * 100, 100)

    req_score = 100
    resume_lower = resume_content.lower()

    required = requirements.get("required_skills", [])
    if required:
        matched_reqs = sum(1 for r in required if any(w in resume_lower for w in r.split() if len(w) > 3))
        req_score = (matched_reqs / len(required)) * 100

    overall = round(kw_score * 0.6 + req_score * 0.4)
    return min(overall, 100)


def _generate_suggestions(
    missing: Set[str],
    requirements: Dict[str, List[str]],
    resume_content: str,
) -> List[Dict[str, str]]:
    suggestions: List[Dict[str, str]] = []
    resume_lower = resume_content.lower()

    tech_missing = sorted(kw for kw in missing if any(c in kw for c in ".+#") or len(kw) <= 10)[:10]
    if tech_missing:
        suggestions.append(
            {
                "section": "skills",
                "action": "add",
                "detail": f"Add missing technical keywords: {', '.join(tech_missing)}",
            }
        )

    for req in requirements.get("required_skills", []):
        req_words = [w for w in req.split() if len(w) > 3]
        if not any(w in resume_lower for w in req_words):
            suggestions.append(
                {
                    "section": "experience",
                    "action": "add",
                    "detail": f"Address required skill: {req}",
                }
            )

    for qual in requirements.get("qualifications", []):
        if qual not in resume_lower:
            suggestions.append(
                {
                    "section": "education",
                    "action": "verify",
                    "detail": f"Ensure qualification is visible: {qual}",
                }
            )

    return suggestions[:15]


def _score_to_grade(score: int) -> str:
    if score >= 85:
        return "Strong Match"
    elif score >= 70:
        return "Good Match"
    elif score >= 50:
        return "Partial Match"
    else:
        return "Weak Match"
