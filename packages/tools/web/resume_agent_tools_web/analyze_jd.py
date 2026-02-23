"""Analyze a job description against a resume.

Wraps :func:`resume_agent_domain.job_matcher.match_job` and its helpers
so the web layer can trigger JD analysis through the standard tool interface.
"""

from __future__ import annotations

from resume_agent_core.tools.base import BaseTool, ToolResult
from resume_agent_domain.job_matcher import JobMatchResult, match_job


class AnalyzeJDTool(BaseTool):
    """Extract keywords and matching suggestions from a job description."""

    name = "analyze_jd"
    description = (
        "Compare a resume against a job description to find matching skills, "
        "missing keywords, and generate tailored improvement suggestions."
    )
    parameters = {
        "resume_text": {
            "type": "string",
            "description": "Resume content as plain text or Markdown",
            "required": True,
        },
        "job_description": {
            "type": "string",
            "description": "Job description text",
            "required": True,
        },
    }

    async def execute(
        self,
        resume_text: str,
        job_description: str,
    ) -> ToolResult:
        if not resume_text.strip():
            return ToolResult(success=False, output="", error="resume_text is empty")
        if not job_description.strip():
            return ToolResult(success=False, output="", error="job_description is empty")

        result = match_job(resume_text, job_description)

        output = _format_report(result)
        return ToolResult(
            success=True,
            output=output,
            data={
                "match_score": result.match_score,
                "matched_keywords": sorted(result.matched_keywords),
                "missing_keywords": sorted(result.missing_keywords),
                "suggestions": result.suggestions,
                "requirements": result.requirements,
            },
        )


def _score_to_grade(score: int) -> str:
    if score >= 85:
        return "Strong Match"
    elif score >= 70:
        return "Good Match"
    elif score >= 50:
        return "Partial Match"
    return "Weak Match"


def _format_report(result: JobMatchResult) -> str:
    grade = _score_to_grade(result.match_score)
    lines = [f"Job Match Score: {result.match_score}/100 ({grade})", ""]

    if result.matched_keywords:
        top = sorted(result.matched_keywords)[:20]
        lines.append(f"Matching Keywords ({len(result.matched_keywords)}): {', '.join(top)}")
        lines.append("")

    if result.missing_keywords:
        top = sorted(result.missing_keywords)[:20]
        lines.append(f"Missing Keywords ({len(result.missing_keywords)}): {', '.join(top)}")
        lines.append("")

    if any(result.requirements.values()):
        lines.append("Requirements Analysis:")
        for category, items in result.requirements.items():
            if items:
                label = category.replace("_", " ").title()
                lines.append(f"  {label}:")
                for item in items:
                    lines.append(f"    - {item}")
        lines.append("")

    if result.suggestions:
        lines.append("Suggestions:")
        for i, s in enumerate(result.suggestions, 1):
            lines.append(f"  {i}. [{s['section']}] {s['detail']}")

    return "\n".join(lines)
