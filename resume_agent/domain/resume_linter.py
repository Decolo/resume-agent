"""Pure domain logic for resume linting (structure, formatting, keyword checks).

All functions operate on content strings -- no file I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .linting import RuleContext, build_default_runner, decide_language, parse_resume_ast

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LINT_KEYWORDS: Dict[str, List[str]] = {
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

LINT_WEIGHTS: Dict[str, float] = {
    "formatting": 0.20,
    "completeness": 0.25,
    "keywords": 0.30,
    "structure": 0.25,
}


@dataclass
class LintResult:
    """Structured result from resume linting."""

    overall_score: int
    formatting: Tuple[int, List[str]]
    completeness: Tuple[int, List[str]]
    keywords: Tuple[int, List[str]]
    structure: Tuple[int, List[str]]
    suggestions: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def lint_resume(
    content: str,
    job_description: str = "",
    lang: str = "auto",
    enable_nlp: bool = True,
    strict_scope: bool = True,
) -> LintResult:
    """Lint resume *content* for structure, formatting, and keyword quality.

    Returns a :class:`LintResult` with per-category breakdowns.
    Optionally accepts *job_description* for keyword matching.
    """
    ast = parse_resume_ast(content)
    lang_decision = decide_language(content, requested_lang=lang, enable_nlp=enable_nlp)
    runner = build_default_runner()
    rule_findings = runner.run(
        ast=ast,
        context=RuleContext(
            lang=lang_decision.lang,
            nlp=lang_decision.nlp,
            nlp_backend=lang_decision.nlp_backend,
            strict_scope=strict_scope,
        ),
    )

    fmt_score, fmt_issues = _check_formatting(content)
    comp_score, comp_issues = _check_completeness(content, lang=lang_decision.lang)
    kw_score, kw_issues = _check_keywords(
        content,
        ast,
        job_description,
        strict_scope,
        lang=lang_decision.lang,
    )
    struct_score, struct_issues = _check_structure(content)
    kw_score, kw_issues = _apply_rule_findings(
        score=kw_score,
        issues=kw_issues,
        findings=rule_findings,
        category="keywords",
    )
    struct_score, struct_issues = _apply_rule_findings(
        score=struct_score,
        issues=struct_issues,
        findings=rule_findings,
        category="structure",
    )

    overall = round(
        fmt_score * LINT_WEIGHTS["formatting"]
        + comp_score * LINT_WEIGHTS["completeness"]
        + kw_score * LINT_WEIGHTS["keywords"]
        + struct_score * LINT_WEIGHTS["structure"]
    )

    suggestions: List[str] = []
    for issues in [fmt_issues, comp_issues, kw_issues, struct_issues]:
        suggestions.extend(issues)
    if lang_decision.detector != "manual":
        suggestions.append(
            f"Language route: {lang_decision.lang} ({lang_decision.detector}); NLP backend: {lang_decision.nlp_backend}"
        )

    return LintResult(
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


def format_lint_report(result: LintResult) -> str:
    """Render a :class:`LintResult` as a human-readable report."""
    grade = _score_to_grade(result.overall_score)
    bar = _score_bar(result.overall_score)

    fmt_score = result.formatting[0]
    comp_score = result.completeness[0]
    kw_score = result.keywords[0]
    struct_score = result.structure[0]

    lines = [
        f"## Lint Score: {result.overall_score}/100 {grade}",
        bar,
        "",
        "| Category     | Score | Weight |",
        "|-------------|-------|--------|",
        f"| Formatting   | {fmt_score:3d}   | {LINT_WEIGHTS['formatting']:.0%}  |",
        f"| Completeness | {comp_score:3d}   | {LINT_WEIGHTS['completeness']:.0%}  |",
        f"| Keywords     | {kw_score:3d}   | {LINT_WEIGHTS['keywords']:.0%}  |",
        f"| Structure    | {struct_score:3d}   | {LINT_WEIGHTS['structure']:.0%}  |",
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


def _check_completeness(content: str, lang: str = "en") -> Tuple[int, List[str]]:
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
        "experience": [
            "experience",
            "work history",
            "employment",
            "professional experience",
            "工作经历",
            "工作经验",
        ],
        "education": ["education", "academic", "教育", "学历"],
        "skills": ["skills", "technical skills", "core competencies", "技能", "专业技能", "技术栈"],
    }
    optional_sections = {
        "summary": ["summary", "objective", "profile", "about me", "简介", "个人简介"],
        "projects": ["projects", "portfolio", "项目", "项目经验"],
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
        r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*[\s,]+\d{4}|\d{4}\s*[-–—]\s*(?:\d{4}|present|current)|\d{4}\s*年(?:\s*\d{1,2}\s*月)?)",
        content_lower,
    )
    if not date_patterns:
        score -= 10
        issues.append("No dates found -- include employment dates (e.g., 'Jan 2020 - Present')")

    return max(0, score), issues


def _check_keywords(
    content: str,
    ast,
    job_description: str = "",
    strict_scope: bool = True,
    lang: str = "en",
) -> Tuple[int, List[str]]:
    score = 100
    issues: List[str] = []
    resume_words = _extract_keywords(content, lang=lang)

    if strict_scope:
        focus_bullets = ast.get_experience_bullets() if ast.has_experience_section else []
    else:
        focus_bullets = ast.bullets
    if strict_scope and not ast.has_experience_section:
        score -= 35
        issues.append("Cannot evaluate experience bullet quality because the experience section is missing")
    if focus_bullets and lang == "en":
        focus_text = "\n".join(focus_bullets).lower()
        found_verbs = [v for v in LINT_KEYWORDS["action_verbs"] if v in focus_text]
        verb_ratio = len(found_verbs) / max(len(LINT_KEYWORDS["action_verbs"]), 1)
        if verb_ratio < 0.2:
            score -= 20
            issues.append(
                "Few action verbs found in experience bullets -- use strong verbs like: Led, Developed, Implemented, Achieved"
            )
        elif verb_ratio < 0.4:
            score -= 10
            issues.append(
                "Could use more action verbs in experience bullets -- try: Optimized, Streamlined, Delivered, Launched"
            )

    numbers = re.findall(
        r"\d+[%$kKmMbB]|\$[\d,]+|\d+\+?\s*(?:years?|months?|clients?|users?|projects?)",
        "\n".join(focus_bullets) if focus_bullets else "",
    )
    if focus_bullets:
        if not numbers:
            score -= 20
            issues.append(
                "No quantifiable achievements in experience bullets -- add metrics (e.g., 'Increased revenue by 25%')"
            )
        elif len(numbers) < 3:
            score -= 10
            issues.append(f"Only {len(numbers)} metric(s) found in experience bullets -- aim for at least 3-5")

    if job_description.strip():
        jd_keywords = _extract_keywords(job_description, lang=lang)
        if not jd_keywords:
            return max(0, score), issues

        matched = jd_keywords & resume_words
        missing = jd_keywords - resume_words

        match_rate = len(matched) / max(len(jd_keywords), 1)
        if match_rate < 0.3:
            score -= 35
            top_missing = sorted(missing)[:10]
            issues.append(f"Low job keyword match ({match_rate:.0%}) -- consider adding: {', '.join(top_missing)}")
        elif match_rate < 0.5:
            score -= 20
            top_missing = sorted(missing)[:7]
            issues.append(f"Moderate job keyword match ({match_rate:.0%}) -- missing: {', '.join(top_missing)}")

    return max(0, score), issues


def _extract_keywords(text: str, lang: str = "en") -> set[str]:
    text_lower = text.lower()
    keywords = set(re.findall(r"\b[a-z]{3,}\b", text_lower))

    if lang == "zh":
        # Build CJK bigrams for robust overlap matching on Chinese text.
        chunks = re.findall(r"[\u4e00-\u9fff]{2,}", text)
        for chunk in chunks:
            if len(chunk) == 2:
                keywords.add(chunk)
                continue
            for i in range(len(chunk) - 1):
                keywords.add(chunk[i : i + 2])

    return keywords - _STOP_WORDS


def _apply_rule_findings(
    score: int,
    issues: List[str],
    findings,
    category: str,
) -> Tuple[int, List[str]]:
    adjusted = score
    out = list(issues)
    for finding in findings:
        if finding.category != category:
            continue
        adjusted -= max(0, finding.penalty)
        out.append(f"{finding.message} [rule:{finding.rule_id}]")
    return max(0, adjusted), out


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
