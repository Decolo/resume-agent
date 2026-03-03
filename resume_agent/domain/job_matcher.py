"""Pure domain logic for job description matching against resumes.

All functions operate on content strings -- no file I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .semantic_similarity import similarity_matrix

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

_PHRASE_KEYWORDS = {
    "machine learning",
    "deep learning",
    "data science",
    "project management",
    "full stack",
    "front end",
    "back end",
    "cloud computing",
    "continuous integration",
    "continuous delivery",
    "natural language processing",
    "computer vision",
}

_LAYER_WEIGHTS = {
    "skills": 0.45,
    "yoe": 0.20,
    "location": 0.20,
    "company_experience": 0.15,
}
_SKILL_WEIGHTS = {"keyword": 0.25, "requirement": 0.25, "semantic": 0.50}
_SKILL_FALLBACK_WEIGHTS = {"keyword": 0.55, "requirement": 0.45, "semantic": 0.0}
_SEMANTIC_GAP_THRESHOLD = 0.45

_LOCATION_MODE_TOKENS = {
    "remote": {"remote", "remotely", "distributed", "anywhere"},
    "hybrid": {"hybrid"},
    "onsite": {"onsite", "on-site", "office"},
}
_LOCATION_TERMS = {
    "san francisco",
    "bay area",
    "new york",
    "nyc",
    "seattle",
    "austin",
    "boston",
    "los angeles",
    "chicago",
    "london",
    "singapore",
    "tokyo",
    "europe",
    "usa",
    "united states",
}

_DOMAIN_MARKERS = {
    "saas": {"saas", "subscription", "b2b"},
    "fintech": {"fintech", "payments", "banking", "trading"},
    "healthcare": {"healthcare", "clinical", "ehr", "medical"},
    "ecommerce": {"ecommerce", "marketplace", "retail", "shopping"},
    "infra": {"infrastructure", "distributed", "microservices"},
    "ai_ml": {"machine learning", "deep learning", "nlp", "computer vision", "ai"},
}
_DOMAIN_WEIGHTS = {
    "saas": 1.0,
    "fintech": 1.0,
    "healthcare": 1.0,
    "ecommerce": 1.0,
    "infra": 0.35,
    "ai_ml": 0.8,
}

_DEGREE_TERMS = {"bachelor", "master", "phd", "degree", "mba", "b.s", "m.s"}
_YEAR_TERMS = {"year", "years", "yr", "yrs"}


@dataclass
class JobMatchResult:
    """Structured result from job matching."""

    match_score: int
    matched_keywords: Set[str]
    missing_keywords: Set[str]
    extra_keywords: Set[str]
    requirements: Dict[str, List[str]]
    suggestions: List[Dict[str, str]] = field(default_factory=list)
    keyword_score: int = 0
    requirement_score: int = 0
    semantic_score: Optional[int] = None
    location_score: int = 50
    skill_score: int = 0
    yoe_score: int = 50
    company_experience_score: int = 50
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    skill_breakdown: Dict[str, float] = field(default_factory=dict)
    semantic_evidence: List[Dict[str, str | float]] = field(default_factory=list)
    backend_info: Dict[str, str] = field(default_factory=dict)
    quick_insights: List[str] = field(default_factory=list)
    next_step: str = "Ask for deep LLM analysis for full contextual review."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def match_job(resume_content: str, job_description: str) -> JobMatchResult:
    """Compare *resume_content* against *job_description* with layered scoring."""
    resume_kw = extract_keywords(resume_content)
    jd_kw = extract_keywords(job_description)
    requirements = extract_requirements(job_description)

    matched = resume_kw & jd_kw
    missing = jd_kw - resume_kw
    extra = resume_kw - jd_kw

    keyword_score = _keyword_overlap_score(resume_kw, jd_kw)
    semantic_score, semantic_evidence, backend_info = _semantic_alignment(requirements, job_description, resume_content)
    requirement_score = _requirement_alignment_score(requirements, resume_content, semantic_evidence)

    skill_score, skill_breakdown = _skill_score(keyword_score, requirement_score, semantic_score)
    location_score = _location_score(job_description, resume_content)
    yoe_score = _yoe_score(job_description, resume_content)
    company_score = _company_experience_score(job_description, resume_content)

    overall = round(
        skill_score * _LAYER_WEIGHTS["skills"]
        + yoe_score * _LAYER_WEIGHTS["yoe"]
        + location_score * _LAYER_WEIGHTS["location"]
        + company_score * _LAYER_WEIGHTS["company_experience"]
    )
    overall = max(0, min(100, overall))

    suggestions = _generate_suggestions(
        missing=missing,
        requirements=requirements,
        semantic_evidence=semantic_evidence,
        location_score=location_score,
        yoe_score=yoe_score,
        company_score=company_score,
    )

    quick_insights = _build_quick_insights(
        skill_score=skill_score,
        location_score=location_score,
        yoe_score=yoe_score,
        company_score=company_score,
    )

    return JobMatchResult(
        match_score=overall,
        matched_keywords=matched,
        missing_keywords=missing,
        extra_keywords=extra,
        requirements=requirements,
        suggestions=suggestions,
        keyword_score=keyword_score,
        requirement_score=requirement_score,
        semantic_score=semantic_score,
        location_score=location_score,
        skill_score=skill_score,
        yoe_score=yoe_score,
        company_experience_score=company_score,
        score_breakdown=dict(_LAYER_WEIGHTS),
        skill_breakdown=skill_breakdown,
        semantic_evidence=semantic_evidence,
        backend_info=backend_info,
        quick_insights=quick_insights,
    )


def extract_keywords(text: str) -> Set[str]:
    """Extract meaningful keywords from *text*, filtering stop words."""
    lowered = (text or "").lower()
    words = {token for token in _tokenize_words(lowered) if len(token) >= 3}
    words = words - _STOP_WORDS
    for phrase in _PHRASE_KEYWORDS:
        if phrase in lowered:
            words.add(phrase)
    return words


def extract_requirements(jd: str) -> Dict[str, List[str]]:
    """Extract structured requirements from job description text without regex matching."""
    reqs: Dict[str, List[str]] = {
        "required_skills": [],
        "preferred_skills": [],
        "qualifications": [],
    }
    section = ""
    for raw_line in (jd or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        normalized = _normalize_text(line)
        if _is_heading(normalized, {"requirements", "required", "must have", "must-have", "qualifications"}):
            section = "required_skills"
            continue
        if _is_heading(normalized, {"preferred", "nice to have", "bonus", "desired"}):
            section = "preferred_skills"
            continue
        if _looks_like_heading(normalized):
            section = ""
            continue

        item = _strip_bullet(line)
        if not item:
            continue
        if section == "required_skills":
            reqs["required_skills"].append(item)
        elif section == "preferred_skills":
            reqs["preferred_skills"].append(item)

    for unit in _split_text_units(jd, max_items=60):
        unit_lower = _normalize_text(unit)
        if any(term in unit_lower for term in _DEGREE_TERMS):
            reqs["qualifications"].append(unit.strip())
            continue
        years = _extract_year_values(unit)
        if years:
            reqs["qualifications"].append(f"{max(years)}+ years experience")

    reqs["required_skills"] = _unique_keep_order(reqs["required_skills"])
    reqs["preferred_skills"] = _unique_keep_order(reqs["preferred_skills"])
    reqs["qualifications"] = _unique_keep_order(reqs["qualifications"])
    return reqs


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_match_report(result: JobMatchResult) -> str:
    """Render a :class:`JobMatchResult` as a human-readable report."""
    grade = _score_to_grade(result.match_score)
    lines = [f"## Job Match Score: {result.match_score}/100 {grade}", ""]

    lines.append("### Layer Scores (Quick Analysis)")
    lines.append(f"- Skills fit: {result.skill_score}/100")
    lines.append(f"- YOE fit: {result.yoe_score}/100")
    lines.append(f"- Location fit: {result.location_score}/100")
    lines.append(f"- Company/domain fit: {result.company_experience_score}/100")
    lines.append("")

    lines.append("### Skill Scoring Signals")
    lines.append(f"- Keyword overlap: {result.keyword_score}/100")
    lines.append(f"- Requirement coverage: {result.requirement_score}/100")
    if result.semantic_score is None:
        reason = result.backend_info.get("reason", "semantic backend unavailable")
        lines.append(f"- Semantic alignment: unavailable ({reason})")
    else:
        lines.append(f"- Semantic alignment: {result.semantic_score}/100")
    lines.append("")

    if result.quick_insights:
        lines.append("### Quick Insights")
        for insight in result.quick_insights:
            lines.append(f"- {insight}")
        lines.append("")

    if result.semantic_evidence:
        lines.append("### Semantic Evidence")
        for item in result.semantic_evidence[:5]:
            lines.append(
                f"- {float(item.get('similarity', 0.0)):.2f} :: JD: {item.get('jd_item', '')} "
                f"=> Resume: {item.get('resume_evidence', '')}"
            )
        lines.append("")

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
        for i, suggestion in enumerate(result.suggestions, 1):
            lines.append(f"{i}. [{suggestion['section']}] {suggestion['detail']}")
        lines.append("")

    lines.append(f"### Next Step\n{result.next_step}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _keyword_overlap_score(resume_kw: Set[str], jd_kw: Set[str]) -> int:
    if not jd_kw:
        return 50
    return round(min(len(resume_kw & jd_kw) / max(len(jd_kw), 1) * 100, 100))


def _requirement_alignment_score(
    requirements: Dict[str, List[str]],
    resume_content: str,
    semantic_evidence: List[Dict[str, str | float]] | None = None,
) -> int:
    required = requirements.get("required_skills", [])
    if not required:
        return 70
    resume_keywords = extract_keywords(resume_content)
    semantic_map = {}
    for item in semantic_evidence or []:
        semantic_map[_normalize_text(str(item.get("jd_item", "")))] = float(item.get("similarity", 0.0))

    covered = 0
    for req in required:
        req_keywords = extract_keywords(req)
        semantic_hit = semantic_map.get(_normalize_text(req), 0.0) >= 0.50
        if semantic_hit or (req_keywords and (req_keywords & resume_keywords)):
            covered += 1
    return round(covered / len(required) * 100)


def _semantic_alignment(
    requirements: Dict[str, List[str]],
    job_description: str,
    resume_content: str,
) -> tuple[Optional[int], List[Dict[str, str | float]], Dict[str, str]]:
    jd_items = list(requirements.get("required_skills", [])) + list(requirements.get("preferred_skills", []))
    if not jd_items:
        jd_items = _split_text_units(job_description, max_items=24)
    resume_items = _split_text_units(resume_content, max_items=32)
    if not jd_items or not resume_items:
        return None, [], {"backend": "local-ngram", "status": "unavailable", "reason": "insufficient text"}

    matrix, backend = similarity_matrix(jd_items, resume_items)
    if not matrix:
        return None, [], {"backend": backend.backend, "status": backend.status, "reason": backend.reason}

    row_max_scores: List[float] = []
    evidence: List[Dict[str, str | float]] = []
    for idx, row in enumerate(matrix):
        if not row:
            continue
        best_idx = max(range(len(row)), key=row.__getitem__)
        best_score = float(row[best_idx])
        row_max_scores.append(best_score)
        evidence.append(
            {
                "jd_item": jd_items[idx],
                "resume_evidence": resume_items[best_idx],
                "similarity": round(best_score, 3),
            }
        )

    if not row_max_scores:
        return None, [], {"backend": backend.backend, "status": "unavailable", "reason": "no semantic scores"}

    semantic_score = round(sum(row_max_scores) / len(row_max_scores) * 100)
    semantic_score = max(0, min(100, semantic_score))
    evidence.sort(key=lambda item: float(item["similarity"]), reverse=True)
    backend_info = {"backend": backend.backend, "status": backend.status}
    if backend.reason:
        backend_info["reason"] = backend.reason
    return semantic_score, evidence[:8], backend_info


def _skill_score(
    keyword_score: int,
    requirement_score: int,
    semantic_score: Optional[int],
) -> tuple[int, Dict[str, float]]:
    weights = _SKILL_WEIGHTS if semantic_score is not None else _SKILL_FALLBACK_WEIGHTS
    score = round(
        keyword_score * weights["keyword"]
        + requirement_score * weights["requirement"]
        + (semantic_score or 0) * weights["semantic"]
    )
    return max(0, min(100, score)), dict(weights)


def _location_score(job_description: str, resume_content: str) -> int:
    jd_lower = _normalize_text(job_description)
    resume_lower = _normalize_text(resume_content)
    jd_modes = _extract_modes(jd_lower)
    resume_modes = _extract_modes(resume_lower)
    jd_terms = {term for term in _LOCATION_TERMS if term in jd_lower}
    resume_terms = {term for term in _LOCATION_TERMS if term in resume_lower}

    score = 65
    if jd_modes:
        if "onsite" in jd_modes and "remote" in resume_modes and "onsite" not in resume_modes:
            return 25
        if "remote" in jd_modes and "onsite" in resume_modes and "remote" not in resume_modes:
            score = 45
        elif jd_modes & resume_modes:
            score = 88
        else:
            score = 72

    if jd_terms:
        if jd_terms & resume_terms:
            score += 10
        elif resume_terms:
            score -= 10

    return max(0, min(100, score))


def _extract_modes(text: str) -> Set[str]:
    modes: Set[str] = set()
    for mode, hints in _LOCATION_MODE_TOKENS.items():
        if any(hint in text for hint in hints):
            modes.add(mode)
    return modes


def _yoe_score(job_description: str, resume_content: str) -> int:
    jd_years = _extract_year_values(job_description)
    resume_years = _extract_year_values(resume_content)
    req = max(jd_years) if jd_years else None
    have = max(resume_years) if resume_years else None
    if req is None:
        return 70
    if have is None:
        return 55
    if have >= req:
        return min(100, 85 + min(15, (have - req) * 2))
    return max(20, round((have / max(req, 1)) * 100) - 5)


def _extract_year_values(text: str) -> List[int]:
    values: List[int] = []
    tokens = _tokenize_words(_normalize_text(text))
    for idx, token in enumerate(tokens):
        if not token.isdigit():
            continue
        value = int(token)
        if value <= 0 or value > 60:
            continue
        window = tokens[idx + 1 : idx + 4]
        if any(t in _YEAR_TERMS for t in window):
            values.append(value)
    return values


def _company_experience_score(job_description: str, resume_content: str) -> int:
    jd_lower = _normalize_text(job_description)
    resume_lower = _normalize_text(resume_content)
    jd_domains = {name for name, terms in _DOMAIN_MARKERS.items() if any(term in jd_lower for term in terms)}
    resume_domains = {name for name, terms in _DOMAIN_MARKERS.items() if any(term in resume_lower for term in terms)}
    if not jd_domains:
        return 60
    if not resume_domains:
        return 45
    overlap_weight = sum(_DOMAIN_WEIGHTS.get(domain, 1.0) for domain in (jd_domains & resume_domains))
    jd_weight = sum(_DOMAIN_WEIGHTS.get(domain, 1.0) for domain in jd_domains)
    coverage = overlap_weight / max(jd_weight, 1e-6)
    return round(40 + coverage * 60)


def _generate_suggestions(
    missing: Set[str],
    requirements: Dict[str, List[str]],
    semantic_evidence: List[Dict[str, str | float]],
    location_score: int,
    yoe_score: int,
    company_score: int,
) -> List[Dict[str, str]]:
    suggestions: List[Dict[str, str]] = []
    tech_missing = sorted(kw for kw in missing if len(kw) <= 14)[:10]
    if tech_missing:
        suggestions.append(
            {
                "section": "skills",
                "action": "add",
                "detail": f"Add or better highlight missing keywords: {', '.join(tech_missing)}",
            }
        )

    for req in requirements.get("required_skills", []):
        suggestions.append(
            {
                "section": "experience",
                "action": "align",
                "detail": f"Add evidence bullets for required capability: {req}",
            }
        )
        if len(suggestions) >= 8:
            break

    for item in semantic_evidence:
        if float(item.get("similarity", 0.0)) < _SEMANTIC_GAP_THRESHOLD:
            suggestions.append(
                {
                    "section": "experience",
                    "action": "clarify",
                    "detail": f"Strengthen alignment for: {item.get('jd_item', '')}",
                }
            )

    if location_score < 55:
        suggestions.append(
            {
                "section": "summary",
                "action": "clarify",
                "detail": "Clarify location/work-mode flexibility to match the role constraints.",
            }
        )
    if yoe_score < 60:
        suggestions.append(
            {
                "section": "experience",
                "action": "quantify",
                "detail": "Make years of relevant experience explicit in role summaries and bullets.",
            }
        )
    if company_score < 55:
        suggestions.append(
            {
                "section": "experience",
                "action": "contextualize",
                "detail": "Emphasize domain context (industry, product type, scale) in past projects.",
            }
        )

    unique = []
    seen = set()
    for suggestion in suggestions:
        key = suggestion["detail"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(suggestion)
    return unique[:15]


def _build_quick_insights(skill_score: int, location_score: int, yoe_score: int, company_score: int) -> List[str]:
    insights = []
    if skill_score >= 80:
        insights.append("Skills are strongly aligned with JD requirements.")
    elif skill_score < 60:
        insights.append("Skill alignment is the main gap; prioritize requirement-to-evidence mapping.")
    if yoe_score < 60:
        insights.append("YOE alignment is weak or unclear; add explicit year counts.")
    if location_score < 60:
        insights.append("Location/work-mode fit may block this role.")
    if company_score < 60:
        insights.append("Domain/company-context overlap is limited; add contextual achievements.")
    if not insights:
        insights.append("All quick-check layers are in a healthy range.")
    return insights


def _strip_bullet(line: str) -> str:
    text = line.strip()
    for prefix in ("- ", "* ", "• "):
        if text.startswith(prefix):
            return text[len(prefix) :].strip()

    idx = 0
    while idx < len(text) and text[idx].isdigit():
        idx += 1
    if idx > 0 and idx + 1 < len(text) and text[idx] in (".", ")") and text[idx + 1] == " ":
        return text[idx + 2 :].strip()
    return text


def _normalize_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def _looks_like_heading(line: str) -> bool:
    if line.endswith(":"):
        return True
    words = line.split()
    return len(words) <= 4 and all(word.isalpha() for word in words)


def _is_heading(line: str, labels: Set[str]) -> bool:
    normalized = line.strip().rstrip(":")
    return any(normalized.startswith(label) for label in labels)


def _split_text_units(text: str, max_items: int = 24) -> List[str]:
    units: List[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        units.append(_strip_bullet(stripped))
        if len(units) >= max_items:
            break
    return _unique_keep_order([unit for unit in units if len(unit) >= 10])


def _tokenize_words(text: str) -> List[str]:
    separators = ",;:!?()[]{}<>/\\|\"'`~@#$%^&*=+"
    table = str.maketrans({ch: " " for ch in separators})
    clean = (text or "").replace("-", " ").replace("_", " ").replace(".", " ").translate(table)
    return [part for part in clean.split() if part]


def _unique_keep_order(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        key = _normalize_text(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _score_to_grade(score: int) -> str:
    if score >= 85:
        return "Strong Match"
    if score >= 70:
        return "Good Match"
    if score >= 50:
        return "Partial Match"
    return "Weak Match"
