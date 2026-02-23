"""Export a resume to various file formats.

Wraps the pure conversion functions from :mod:`resume_agent_domain.resume_writer`
and writes the result to disk.  Deterministic -- no LLM involved.
"""

from __future__ import annotations

from pathlib import Path

from resume_agent_core.tools.base import BaseTool, ToolResult
from resume_agent_domain.resume_writer import (
    markdown_to_html,
    markdown_to_json_resume,
    markdown_to_plain_text,
)


class ExportResumeTool(BaseTool):
    """Convert Markdown resume content and write to a file."""

    name = "export_resume"
    description = (
        "Export resume content (Markdown) to a file in the specified format. " "Supported: .md, .txt, .json, .html"
    )
    parameters = {
        "path": {
            "type": "string",
            "description": "Output file path (extension determines format)",
            "required": True,
        },
        "content": {
            "type": "string",
            "description": "Resume content in Markdown format",
            "required": True,
        },
        "css": {
            "type": "string",
            "description": "Custom CSS for HTML output (optional)",
        },
    }

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).resolve()

    async def execute(
        self,
        path: str,
        content: str,
        css: str | None = None,
    ) -> ToolResult:
        try:
            file_path = self._resolve_path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            suffix = file_path.suffix.lower()
            converters = {
                ".md": lambda c: c,
                ".txt": markdown_to_plain_text,
                ".json": markdown_to_json_resume,
                ".html": lambda c: markdown_to_html(c, css=css),
            }

            converter = converters.get(suffix)
            if converter is None:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported format: {suffix}. Supported: .md, .txt, .json, .html",
                )

            output_content = converter(content)
            file_path.write_text(output_content, encoding="utf-8")

            return ToolResult(
                success=True,
                output=f"Exported resume to {path} ({len(output_content)} chars)",
                data={"path": str(file_path), "format": suffix, "size": len(output_content)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return self.workspace_dir / p
