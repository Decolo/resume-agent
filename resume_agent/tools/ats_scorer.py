"""ATS (Applicant Tracking System) scoring tool for resumes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

from .base import BaseTool, ToolResult

# Common ATS keywords by category
ATS_KEYWORDS = {
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

# Weights for scoring categories
WEIGHTS = {
    "formatting": 0.20,
    "completeness": 0.25,
    "keywords": 0.30,
    "structure": 0.25,
}


class ATSScorerTool(BaseTool):
    """Score a resume for ATS (Applicant Tracking System) compatibility."""

    name = "ats_score"
    description = """Score a resume for ATS compatibility. Returns a structured score (0-100)
with breakdown by formatting, completeness, keywords, and structure.
Optionally accepts a job description for keyword matching."""
    parameters = {
        "path": {
            "type": "string",
            "description": "Path to the resume file to score",
            "required": True,
        },
        "job_description": {
            "type": "string",
            "description": "Optional job description text for keyword matching",
        },
    }

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).resolve()

    async def execute(self, path: str, job_description: str = "") -> ToolResult:
        try:
            file_path = self._resolve_path(path)
            if not file_path.exists():
                return ToolResult(success=False, output="", error=f"File not found: {path}")

            content = file_path.read_text(encoding="utf-8")
            if not content.strip():
                return ToolResult(success=False, output="", error=f"File is empty: {path}")

            # Run all checks
            fmt_score, fmt_issues = self._check_formatting(content)
            comp_score, comp_issues = self._check_completeness(content)
            kw_score, kw_issues = self._check_keywords(content, job_description)
            struct_score, struct_issues = self._check_structure(content)

            # Weighted overall score
            overall = round(
                fmt_score * WEIGHTS["formatting"]
                + comp_score * WEIGHTS["completeness"]
                + kw_score * WEIGHTS["keywords"]
                + struct_score * WEIGHTS["structure"]
            )

            # Build suggestions from issues
            suggestions = []
            for issues in [fmt_issues, comp_issues, kw_issues, struct_issues]:
                suggestions.extend(issues)

            # Format output
            output = self._format_report(overall, fmt_score, comp_score, kw_score, struct_score, suggestions)

            return ToolResult(
                success=True,
                output=output,
                data={
                    "overall_score": overall,
                    "sections": {
                        "formatting": {"score": fmt_score, "issues": fmt_issues},
                        "completeness": {"score": comp_score, "issues": comp_issues},
                        "keywords": {"score": kw_score, "issues": kw_issues},
                        "structure": {"score": struct_score, "issues": struct_issues},
                    },
                    "suggestions": suggestions,
                },
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # --- Scoring checks ---

    def _check_formatting(self, content: str) -> tuple[int, List[str]]:
        """Check formatting for ATS compatibility. Returns (score, issues)."""
        score = 100
        issues: List[str] = []

        # Check for tables (ATS often can't parse them)
        if re.search(r"\|.*\|.*\|", content):
            score -= 15
            issues.append("Contains tables — many ATS systems can't parse table layouts")

        # Check for special characters that confuse ATS
        fancy_chars = re.findall(r"[•●◆★☆►▸▹→←↑↓✓✗✔✘❌✅]", content)
        if fancy_chars:
            score -= 10
            issues.append(
                f"Contains special characters ({', '.join(sorted(set(fancy_chars))[:5])}) — use standard bullets (- or *)"
            )

        # Check for very long lines (>120 chars) suggesting poor formatting
        long_lines = [line for line in content.split("\n") if len(line) > 120]
        if len(long_lines) > 5:
            score -= 10
            issues.append(f"{len(long_lines)} lines exceed 120 characters — consider shorter lines for readability")

        # Check for images/embedded content markers
        if re.search(r"!\[.*?\]\(.*?\)", content):
            score -= 15
            issues.append("Contains embedded images — ATS cannot read images")

        # Check for excessive blank lines
        if re.search(r"\n{4,}", content):
            score -= 5
            issues.append("Excessive blank lines — tighten spacing for cleaner formatting")

        return max(0, score), issues

    def _check_completeness(self, content: str) -> tuple[int, List[str]]:
        """Check for required resume sections and contact info."""
        score = 100
        issues: List[str] = []
        content_lower = content.lower()

        # Check contact info
        has_email = bool(re.search(r"[\w\.\-+]+@[\w\.\-]+\.\w+", content))
        has_phone = bool(re.search(r"[\+]?[\d\-\(\)\s]{10,}", content))
        has_linkedin = "linkedin" in content_lower

        if not has_email:
            score -= 15
            issues.append("Missing email address — essential for recruiter contact")
        if not has_phone:
            score -= 10
            issues.append("Missing phone number — most recruiters expect a phone number")
        if not has_linkedin:
            score -= 5
            issues.append("No LinkedIn URL — consider adding your LinkedIn profile")

        # Check required sections
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
                issues.append(f"Missing '{section_name}' section — this is expected by most ATS systems")

        for section_name, keywords in optional_sections.items():
            if not any(kw in content_lower for kw in keywords):
                score -= 5
                issues.append(f"No '{section_name}' section — recommended for a complete resume")

        # Check for dates in experience
        date_patterns = re.findall(
            r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*[\s,]+\d{4}|\d{4}\s*[-–—]\s*(?:\d{4}|present|current))",
            content_lower,
        )
        if not date_patterns:
            score -= 10
            issues.append("No dates found — include employment dates (e.g., 'Jan 2020 - Present')")

        return max(0, score), issues

    def _check_keywords(self, content: str, job_description: str = "") -> tuple[int, List[str]]:
        """Check keyword density and job-specific matching."""
        score = 100
        issues: List[str] = []
        content_lower = content.lower()
        words = re.findall(r"\b[a-z]+\b", content_lower)

        # Check for action verbs
        found_verbs = [v for v in ATS_KEYWORDS["action_verbs"] if v in content_lower]
        verb_ratio = len(found_verbs) / max(len(ATS_KEYWORDS["action_verbs"]), 1)
        if verb_ratio < 0.2:
            score -= 20
            issues.append("Few action verbs found — use strong verbs like: Led, Developed, Implemented, Achieved")
        elif verb_ratio < 0.4:
            score -= 10
            issues.append("Could use more action verbs — try: Optimized, Streamlined, Delivered, Launched")

        # Check for quantifiable achievements
        numbers = re.findall(r"\d+[%$kKmMbB]|\$[\d,]+|\d+\+?\s*(?:years?|months?|clients?|users?|projects?)", content)
        if not numbers:
            score -= 20
            issues.append("No quantifiable achievements — add metrics (e.g., 'Increased revenue by 25%')")
        elif len(numbers) < 3:
            score -= 10
            issues.append(f"Only {len(numbers)} metric(s) found — aim for at least 3-5 quantified achievements")

        # Job description keyword matching (if provided)
        if job_description.strip():
            jd_lower = job_description.lower()
            jd_words = set(re.findall(r"\b[a-z]{3,}\b", jd_lower))
            # Filter out common stop words
            stop_words = {
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
            jd_keywords = jd_words - stop_words
            resume_words = set(words)

            matched = jd_keywords & resume_words
            missing = jd_keywords - resume_words

            match_rate = len(matched) / max(len(jd_keywords), 1)
            if match_rate < 0.3:
                score -= 25
                top_missing = sorted(missing)[:10]
                issues.append(f"Low job keyword match ({match_rate:.0%}) — consider adding: {', '.join(top_missing)}")
            elif match_rate < 0.5:
                score -= 15
                top_missing = sorted(missing)[:7]
                issues.append(f"Moderate job keyword match ({match_rate:.0%}) — missing: {', '.join(top_missing)}")

        return max(0, score), issues

    def _check_structure(self, content: str) -> tuple[int, List[str]]:
        """Check resume structure and consistency."""
        score = 100
        issues: List[str] = []
        lines = content.split("\n")

        # Check for section headers (markdown # or ## style, or ALL CAPS)
        headers = [
            line for line in lines if re.match(r"^#{1,3}\s+\S", line) or (line.isupper() and len(line.strip()) > 3)
        ]
        if len(headers) < 3:
            score -= 15
            issues.append("Few section headers found — use clear headers (## Experience, ## Education, etc.)")

        # Check bullet point consistency
        bullet_styles = set()
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
            issues.append(f"Inconsistent bullet styles ({', '.join(bullet_styles)}) — pick one style throughout")

        # Check resume length
        word_count = len(content.split())
        if word_count < 150:
            score -= 15
            issues.append(f"Resume is very short ({word_count} words) — most resumes should be 300-800 words")
        elif word_count > 1200:
            score -= 10
            issues.append(f"Resume is long ({word_count} words) — consider trimming to 1-2 pages (300-800 words)")

        # Check for consistent date formatting
        date_formats = set()
        if re.search(r"\b\d{1,2}/\d{4}\b", content):
            date_formats.add("MM/YYYY")
        if re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}\b", content):
            date_formats.add("Month YYYY")
        if re.search(r"\b\d{4}-\d{2}\b", content):
            date_formats.add("YYYY-MM")
        if len(date_formats) > 1:
            score -= 5
            issues.append(f"Mixed date formats ({', '.join(date_formats)}) — use one consistent format")

        return max(0, score), issues

    # --- Output formatting ---

    def _format_report(
        self,
        overall: int,
        fmt_score: int,
        comp_score: int,
        kw_score: int,
        struct_score: int,
        suggestions: List[str],
    ) -> str:
        """Format the ATS score report as readable text."""
        grade = self._score_to_grade(overall)
        bar = self._score_bar(overall)

        lines = [
            f"## ATS Score: {overall}/100 {grade}",
            bar,
            "",
            "| Category     | Score | Weight |",
            "|-------------|-------|--------|",
            f"| Formatting   | {fmt_score:3d}   | {WEIGHTS['formatting']:.0%}  |",
            f"| Completeness | {comp_score:3d}   | {WEIGHTS['completeness']:.0%}  |",
            f"| Keywords     | {kw_score:3d}   | {WEIGHTS['keywords']:.0%}  |",
            f"| Structure    | {struct_score:3d}   | {WEIGHTS['structure']:.0%}  |",
        ]

        if suggestions:
            lines.append("")
            lines.append("### Suggestions")
            for i, s in enumerate(suggestions, 1):
                lines.append(f"{i}. {s}")

        return "\n".join(lines)

    @staticmethod
    def _score_to_grade(score: int) -> str:
        if score >= 90:
            return "🟢 Excellent"
        elif score >= 75:
            return "🟡 Good"
        elif score >= 60:
            return "🟠 Fair"
        else:
            return "🔴 Needs Work"

    @staticmethod
    def _score_bar(score: int, width: int = 20) -> str:
        filled = round(score / 100 * width)
        return f"[{'█' * filled}{'░' * (width - filled)}]"

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return self.workspace_dir / p
