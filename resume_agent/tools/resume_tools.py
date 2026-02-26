"""Resume domain tools - wrap pure domain functions as BaseTool instances.

Each tool handles file I/O (reading content from disk) and delegates
the actual resume logic to ``resume_agent.domain``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple

from resume_agent.core.tools.base import BaseTool, ToolResult
from resume_agent.domain.ats_scorer import format_ats_report, score_ats
from resume_agent.domain.job_matcher import format_match_report, match_job
from resume_agent.domain.resume_parser import extract_sections, json_resume_to_text
from resume_agent.domain.resume_validator import (
    format_validation_report,
    validate_resume,
)
from resume_agent.domain.resume_writer import (
    markdown_to_html,
    markdown_to_json_resume,
    markdown_to_plain_text,
)

# ---------------------------------------------------------------------------
# ResumeParserTool
# ---------------------------------------------------------------------------


class ResumeParserTool(BaseTool):
    """Parse resume files into structured data."""

    name = "resume_parse"
    description = (
        "Parse a resume file (PDF, DOCX, MD, TXT, JSON) and extract its content. "
        "Returns structured text that can be analyzed and modified."
    )
    parameters = {
        "path": {
            "type": "string",
            "description": "Path to the resume file",
            "required": True,
        },
    }

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).resolve()
        self._cache: Dict[str, Tuple[float, ToolResult]] = {}

    async def execute(self, path: str) -> ToolResult:
        try:
            file_path = self._resolve_path(path)
            if not file_path.exists():
                return ToolResult(success=False, output="", error=f"File not found: {path}")

            current_mtime = file_path.stat().st_mtime
            cache_key = str(file_path)
            if cache_key in self._cache:
                cached_mtime, cached_result = self._cache[cache_key]
                if cached_mtime == current_mtime:
                    return cached_result

            suffix = file_path.suffix.lower()

            if suffix == ".pdf":
                content, metadata = await self._parse_pdf(file_path)
            elif suffix == ".docx":
                content, metadata = await self._parse_docx(file_path)
            elif suffix in [".md", ".txt"]:
                content = file_path.read_text(encoding="utf-8")
                metadata = {"lines": content.count("\n") + 1, "characters": len(content)}
            elif suffix == ".json":
                raw = file_path.read_text(encoding="utf-8")
                data = json.loads(raw)
                content, metadata = json_resume_to_text(data)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported file format: {suffix}. Supported: .pdf, .docx, .md, .txt, .json",
                )

            sections = extract_sections(content)

            output = f"=== Resume Content ===\n{content}\n\n=== Detected Sections ===\n"
            for section, text in sections.items():
                output += f"\n[{section}]\n{text[:200]}{'...' if len(text) > 200 else ''}\n"

            result = ToolResult(
                success=True,
                output=output,
                data={
                    "path": str(file_path),
                    "format": suffix,
                    "sections": list(sections.keys()),
                    "metadata": metadata,
                },
            )
            self._cache[cache_key] = (current_mtime, result)
            return result
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    async def _parse_pdf(self, path: Path) -> Tuple[str, dict]:
        try:
            import fitz
        except ImportError:
            raise ImportError("PyMuPDF not installed. Run: pip install pymupdf")
        doc = fitz.open(path)
        text_parts = [page.get_text() for page in doc]
        metadata = {"pages": len(doc), "title": doc.metadata.get("title", ""), "author": doc.metadata.get("author", "")}
        doc.close()
        return "\n".join(text_parts), metadata

    async def _parse_docx(self, path: Path) -> Tuple[str, dict]:
        try:
            from docx import Document
        except ImportError:
            raise ImportError("python-docx not installed. Run: pip install python-docx")
        doc = Document(path)
        text_parts = [para.text for para in doc.paragraphs if para.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                row_text = "\t".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    text_parts.append(row_text)
        metadata = {"paragraphs": len(doc.paragraphs), "tables": len(doc.tables)}
        return "\n".join(text_parts), metadata

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        return p if p.is_absolute() else self.workspace_dir / p


# ---------------------------------------------------------------------------
# ResumeWriterTool
# ---------------------------------------------------------------------------


class ResumeWriterTool(BaseTool):
    """Write/generate resume files in various formats."""

    name = "resume_write"
    description = (
        "Write resume content to a file in the specified format. "
        "Supported: .md, .txt, .json, .html. "
        "For PDF/DOCX, first write to .md or .html, then convert using bash tool."
    )
    parameters = {
        "path": {
            "type": "string",
            "description": "Output file path (extension determines format)",
            "required": True,
        },
        "content": {
            "type": "string",
            "description": "Resume content to write (Markdown format recommended)",
            "required": True,
        },
        "template": {
            "type": "string",
            "description": "Template style: 'modern', 'classic', 'minimal', 'creative' (for HTML output)",
            "default": "modern",
        },
    }

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).resolve()
        self._preview_manager = None

    async def execute(self, path: str, content: str, template: str = "modern") -> ToolResult:
        try:
            file_path = self._resolve_path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            suffix = file_path.suffix.lower()

            if suffix == ".md":
                output_content = content
            elif suffix == ".txt":
                output_content = markdown_to_plain_text(content)
            elif suffix == ".json":
                output_content = markdown_to_json_resume(content)
            elif suffix == ".html":
                css = self._load_template_css(template)
                output_content = markdown_to_html(content, css=css)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported output format: {suffix}. Supported: .md, .txt, .json, .html",
                )

            if self._preview_manager is not None:
                self._preview_manager.add(path, output_content, file_path)
                return ToolResult(
                    success=True,
                    output=f"Successfully wrote resume to {path} ({len(output_content)} characters)",
                    data={"preview": True, "pending_path": path, "format": suffix},
                )

            file_path.write_text(output_content, encoding="utf-8")
            return ToolResult(
                success=True,
                output=f"Successfully wrote resume to {path} ({len(output_content)} characters)",
                data={"path": str(file_path), "format": suffix, "size": len(output_content)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _load_template_css(self, template: str) -> str | None:
        """Try to load CSS from core templates; return None to use domain fallback."""
        try:
            from resume_agent.core.templates import load_template_css

            return load_template_css(template)
        except Exception:
            return None

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        return p if p.is_absolute() else self.workspace_dir / p


# ---------------------------------------------------------------------------
# ATSScorerTool
# ---------------------------------------------------------------------------


class ATSScorerTool(BaseTool):
    """Score a resume for ATS compatibility."""

    name = "ats_score"
    description = (
        "Score a resume for ATS compatibility. Returns a structured score (0-100) "
        "with breakdown by formatting, completeness, keywords, and structure. "
        "Optionally accepts a job description for keyword matching."
    )
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

            result = score_ats(content, job_description)
            output = format_ats_report(result)

            return ToolResult(
                success=True,
                output=output,
                data={
                    "overall_score": result.overall_score,
                    "sections": {
                        "formatting": {"score": result.formatting[0], "issues": result.formatting[1]},
                        "completeness": {"score": result.completeness[0], "issues": result.completeness[1]},
                        "keywords": {"score": result.keywords[0], "issues": result.keywords[1]},
                        "structure": {"score": result.structure[0], "issues": result.structure[1]},
                    },
                    "suggestions": result.suggestions,
                },
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        return p if p.is_absolute() else self.workspace_dir / p


# ---------------------------------------------------------------------------
# JobMatcherTool
# ---------------------------------------------------------------------------


class JobMatcherTool(BaseTool):
    """Match a resume against a job description and identify gaps."""

    name = "job_match"
    description = (
        "Compare a resume against a job description to find matching skills, "
        "missing keywords, and generate tailored improvement suggestions."
    )
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
            file_path = self._resolve_path(resume_path)
            if not file_path.exists():
                return ToolResult(success=False, output="", error=f"Resume not found: {resume_path}")

            resume_content = file_path.read_text(encoding="utf-8")
            if not resume_content.strip():
                return ToolResult(success=False, output="", error=f"Resume is empty: {resume_path}")

            if not job_text.strip() and not job_url.strip():
                return ToolResult(success=False, output="", error="Provide either job_text or job_url")

            jd = job_text.strip()
            if not jd and job_url.strip():
                return ToolResult(
                    success=False,
                    output="",
                    error="job_url provided but fetching not supported in this tool. "
                    "Use web_read tool first, then pass the text via job_text.",
                )

            result = match_job(resume_content, jd)
            output = format_match_report(result)

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
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        return p if p.is_absolute() else self.workspace_dir / p


# ---------------------------------------------------------------------------
# ResumeValidatorTool
# ---------------------------------------------------------------------------


class ResumeValidatorTool(BaseTool):
    """Validate resume content for completeness and format correctness."""

    name = "resume_validate"
    description = (
        "Validate a resume file for content completeness, format correctness, "
        "encoding issues, and appropriate length. Returns a pass/fail with detailed issues."
    )
    parameters = {
        "path": {
            "type": "string",
            "description": "Path to the resume file to validate",
            "required": True,
        },
    }

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).resolve()

    async def execute(self, path: str) -> ToolResult:
        try:
            file_path = self._resolve_path(path)
            if not file_path.exists():
                return ToolResult(success=False, output="", error=f"File not found: {path}")

            content = file_path.read_text(encoding="utf-8")
            suffix = file_path.suffix.lower()

            result = validate_resume(content, file_format=suffix)
            output = format_validation_report(path, result)

            return ToolResult(
                success=True,
                output=output,
                data={
                    "valid": result.valid,
                    "errors": result.errors,
                    "warnings": result.warnings,
                    "format": suffix,
                },
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        return p if p.is_absolute() else self.workspace_dir / p
