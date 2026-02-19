"""Job description matching tool — compare resume against job requirements."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Set

from .base import BaseTool, ToolResult


class JobMatcherTool(BaseTool):
    """Match a resume against a job description and identify gaps."""

    name = "job_match"
    description = """Compare a resume against a job description to find matching skills,
missing keywords, and generate tailored improvement suggestions.
Provide either job_text directly or job_url to fetch the posting."""
    parameters = {
        "resume_path": {
            "type": "string",
            "description": "Path to the resume file to analyze",
            "required": True,
        },
        "job_text": {
            "type": "string",
            "description": "Job description text (paste directly)",
        },
        "job_url": {
            "type": "string",
            "description": "URL to fetch job description from (requires web_read tool)",
        },
    }

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).resolve()

    async def execute(self, resume_path: str, job_text: str = "", job_url: str = "") -> ToolResult:
        try:
            # Resolve and read resume
            file_path = self._resolve_path(resume_path)
            if not file_path.exists():
                return ToolResult(success=False, output="", error=f"Resume not found: {resume_path}")

            resume_content = file_path.read_text(encoding="utf-8")
            if not resume_content.strip():
                return ToolResult(success=False, output="", error=f"Resume is empty: {resume_path}")

            # Get job description
            if not job_text.strip() and not job_url.strip():
                return ToolResult(
                    success=False,
                    output="",
                    error="Provide either job_text or job_url",
                )

            jd = job_text.strip()
            if not jd and job_url.strip():
                return ToolResult(
                    success=False,
                    output="",
                    error="job_url provided but fetching not supported in this tool. "
                    "Use web_read tool first, then pass the text via job_text.",
                )

            # Extract keywords from both
            resume_keywords = self._extract_keywords(resume_content)
            jd_keywords = self._extract_keywords(jd)
            jd_requirements = self._extract_requirements(jd)

            # Compare
            matched = resume_keywords & jd_keywords
            missing = jd_keywords - resume_keywords
            extra = resume_keywords - jd_keywords

            match_score = self._calculate_match_score(resume_keywords, jd_keywords, jd_requirements, resume_content)

            # Generate suggestions
            suggestions = self._generate_suggestions(missing, jd_requirements, resume_content)

            # Format output
            output = self._format_report(match_score, matched, missing, extra, suggestions, jd_requirements)

            return ToolResult(
                success=True,
                output=output,
                data={
                    "match_score": match_score,
                    "matched_keywords": sorted(matched),
                    "missing_keywords": sorted(missing),
                    "suggestions": suggestions,
                    "requirements": jd_requirements,
                },
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # --- Keyword extraction ---

    # Common words to exclude from keyword matching
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

    def _extract_keywords(self, text: str) -> Set[str]:
        """Extract meaningful keywords from text."""
        words = set(re.findall(r"\b[a-z][a-z\+\#\.]{2,}\b", text.lower()))
        # Also capture multi-word tech terms
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
        return words - self._STOP_WORDS

    def _extract_requirements(self, jd: str) -> Dict[str, List[str]]:
        """Extract structured requirements from job description."""
        reqs: Dict[str, List[str]] = {
            "required_skills": [],
            "preferred_skills": [],
            "qualifications": [],
        }
        jd_lower = jd.lower()

        # Look for requirement patterns
        # "Required: ...", "Must have: ...", "Requirements: ..."
        req_section = re.search(
            r"(?:required|must have|requirements?|qualifications?)[:\s]*\n((?:[-•*]\s*.+\n?)+)",
            jd_lower,
        )
        if req_section:
            items = re.findall(r"[-•*]\s*(.+)", req_section.group(1))
            reqs["required_skills"] = [i.strip() for i in items]

        # "Preferred: ...", "Nice to have: ...", "Bonus: ..."
        pref_section = re.search(
            r"(?:preferred|nice to have|bonus|desired)[:\s]*\n((?:[-•*]\s*.+\n?)+)",
            jd_lower,
        )
        if pref_section:
            items = re.findall(r"[-•*]\s*(.+)", pref_section.group(1))
            reqs["preferred_skills"] = [i.strip() for i in items]

        # Education requirements
        edu_match = re.search(
            r"(?:bachelor|master|phd|degree|b\.?s\.?|m\.?s\.?|mba)[^.]*",
            jd_lower,
        )
        if edu_match:
            reqs["qualifications"].append(edu_match.group().strip())

        # Years of experience
        exp_match = re.search(r"(\d+)\+?\s*years?\s*(?:of\s+)?experience", jd_lower)
        if exp_match:
            reqs["qualifications"].append(f"{exp_match.group(1)}+ years experience")

        return reqs

    def _calculate_match_score(
        self,
        resume_kw: Set[str],
        jd_kw: Set[str],
        requirements: Dict[str, List[str]],
        resume_content: str,
    ) -> int:
        """Calculate overall match score (0-100)."""
        if not jd_kw:
            return 50  # No keywords to match against

        # Keyword overlap (60% weight)
        overlap = len(resume_kw & jd_kw) / max(len(jd_kw), 1)
        kw_score = min(overlap * 100, 100)

        # Requirements coverage (40% weight)
        req_score = 100
        resume_lower = resume_content.lower()

        required = requirements.get("required_skills", [])
        if required:
            matched_reqs = sum(1 for r in required if any(w in resume_lower for w in r.split() if len(w) > 3))
            req_score = (matched_reqs / len(required)) * 100

        overall = round(kw_score * 0.6 + req_score * 0.4)
        return min(overall, 100)

    def _generate_suggestions(
        self,
        missing: Set[str],
        requirements: Dict[str, List[str]],
        resume_content: str,
    ) -> List[Dict[str, str]]:
        """Generate actionable suggestions based on gaps."""
        suggestions: List[Dict[str, str]] = []
        resume_lower = resume_content.lower()

        # Missing keywords
        tech_missing = sorted(kw for kw in missing if any(c in kw for c in ".+#") or len(kw) <= 10)[:10]
        if tech_missing:
            suggestions.append(
                {
                    "section": "skills",
                    "action": "add",
                    "detail": f"Add missing technical keywords: {', '.join(tech_missing)}",
                }
            )

        # Missing required skills
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

        # Missing qualifications
        for qual in requirements.get("qualifications", []):
            if qual not in resume_lower:
                suggestions.append(
                    {
                        "section": "education",
                        "action": "verify",
                        "detail": f"Ensure qualification is visible: {qual}",
                    }
                )

        return suggestions[:15]  # Cap at 15 suggestions

    def _format_report(
        self,
        score: int,
        matched: Set[str],
        missing: Set[str],
        extra: Set[str],
        suggestions: List[Dict[str, str]],
        requirements: Dict[str, List[str]],
    ) -> str:
        """Format the match report as readable text."""
        grade = self._score_to_grade(score)

        lines = [
            f"## Job Match Score: {score}/100 {grade}",
            "",
        ]

        # Matched keywords
        if matched:
            top_matched = sorted(matched)[:20]
            lines.append(f"### ✅ Matching Keywords ({len(matched)})")
            lines.append(", ".join(top_matched))
            lines.append("")

        # Missing keywords
        if missing:
            top_missing = sorted(missing)[:20]
            lines.append(f"### ❌ Missing Keywords ({len(missing)})")
            lines.append(", ".join(top_missing))
            lines.append("")

        # Requirements analysis
        if any(requirements.values()):
            lines.append("### 📋 Requirements Analysis")
            for category, items in requirements.items():
                if items:
                    label = category.replace("_", " ").title()
                    lines.append(f"\n**{label}:**")
                    for item in items:
                        lines.append(f"- {item}")
            lines.append("")

        # Suggestions
        if suggestions:
            lines.append("### 💡 Suggestions")
            for i, s in enumerate(suggestions, 1):
                lines.append(f"{i}. [{s['section']}] {s['detail']}")

        return "\n".join(lines)

    @staticmethod
    def _score_to_grade(score: int) -> str:
        if score >= 85:
            return "🟢 Strong Match"
        elif score >= 70:
            return "🟡 Good Match"
        elif score >= 50:
            return "🟠 Partial Match"
        else:
            return "🔴 Weak Match"

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return self.workspace_dir / p
