"""Resume validator tool — check content quality before export."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from .base import BaseTool, ToolResult


class ResumeValidatorTool(BaseTool):
    """Validate resume content for completeness and format correctness."""

    name = "resume_validate"
    description = """Validate a resume file for content completeness, format correctness,
encoding issues, and appropriate length. Returns a pass/fail with detailed issues."""
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

            issues: List[Dict[str, str]] = []

            # Content checks (all formats)
            issues.extend(self._check_content(content))

            # Format-specific checks
            if suffix == ".html":
                issues.extend(self._check_html(content))
            elif suffix == ".json":
                issues.extend(self._check_json(content))
            elif suffix in (".md", ".txt"):
                issues.extend(self._check_text(content))

            # Determine pass/fail
            errors = [i for i in issues if i["level"] == "error"]
            warnings = [i for i in issues if i["level"] == "warning"]

            passed = len(errors) == 0
            output = self._format_report(path, passed, errors, warnings)

            return ToolResult(
                success=True,
                output=output,
                data={
                    "valid": passed,
                    "errors": errors,
                    "warnings": warnings,
                    "format": suffix,
                },
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _check_content(self, content: str) -> List[Dict[str, str]]:
        """Check content quality regardless of format."""
        issues: List[Dict[str, str]] = []

        if not content.strip():
            issues.append({"level": "error", "check": "empty", "message": "File is empty"})
            return issues

        word_count = len(content.split())
        if word_count < 50:
            issues.append({
                "level": "error",
                "check": "length",
                "message": f"Resume is too short ({word_count} words). Minimum recommended: 150 words.",
            })
        elif word_count < 150:
            issues.append({
                "level": "warning",
                "check": "length",
                "message": f"Resume is short ({word_count} words). Recommended: 300-800 words.",
            })
        elif word_count > 1500:
            issues.append({
                "level": "warning",
                "check": "length",
                "message": f"Resume is long ({word_count} words). Consider trimming to 1-2 pages.",
            })

        # Check for placeholder text
        placeholders = re.findall(
            r"\b(?:TODO|FIXME|XXX|PLACEHOLDER|INSERT|YOUR NAME|COMPANY NAME)\b",
            content, re.IGNORECASE,
        )
        if placeholders:
            issues.append({
                "level": "error",
                "check": "placeholders",
                "message": f"Contains placeholder text: {', '.join(set(placeholders))}",
            })

        # Check for encoding issues (replacement characters)
        if "\ufffd" in content or "â€" in content or "Ã" in content:
            issues.append({
                "level": "error",
                "check": "encoding",
                "message": "Contains encoding artifacts (mojibake). Re-save with UTF-8 encoding.",
            })

        return issues

    def _check_html(self, content: str) -> List[Dict[str, str]]:
        """Validate HTML-specific issues."""
        issues: List[Dict[str, str]] = []

        if "<html" not in content.lower():
            issues.append({
                "level": "error",
                "check": "html_structure",
                "message": "Missing <html> tag — not a valid HTML document.",
            })
        if "<head" not in content.lower():
            issues.append({
                "level": "warning",
                "check": "html_head",
                "message": "Missing <head> section.",
            })
        if "charset" not in content.lower():
            issues.append({
                "level": "warning",
                "check": "html_charset",
                "message": "No charset declaration. Add <meta charset=\"UTF-8\">.",
            })
        if "<style" not in content.lower() and "stylesheet" not in content.lower():
            issues.append({
                "level": "warning",
                "check": "html_styles",
                "message": "No CSS styles found. The resume may look unstyled.",
            })

        return issues

    def _check_json(self, content: str) -> List[Dict[str, str]]:
        """Validate JSON Resume format."""
        import json as json_mod
        issues: List[Dict[str, str]] = []

        try:
            data = json_mod.loads(content)
        except json_mod.JSONDecodeError as e:
            issues.append({
                "level": "error",
                "check": "json_parse",
                "message": f"Invalid JSON: {e}",
            })
            return issues

        if not isinstance(data, dict):
            issues.append({
                "level": "error",
                "check": "json_structure",
                "message": "JSON root must be an object, not an array.",
            })
            return issues

        # Check JSON Resume schema basics
        if "basics" not in data:
            issues.append({
                "level": "warning",
                "check": "json_schema",
                "message": "Missing 'basics' section (JSON Resume standard).",
            })
        else:
            basics = data["basics"]
            if not basics.get("name"):
                issues.append({
                    "level": "warning",
                    "check": "json_name",
                    "message": "Missing name in basics section.",
                })

        return issues

    def _check_text(self, content: str) -> List[Dict[str, str]]:
        """Validate Markdown/text format."""
        issues: List[Dict[str, str]] = []

        lines = content.strip().split("\n")
        if lines and not lines[0].strip():
            issues.append({
                "level": "warning",
                "check": "text_start",
                "message": "File starts with blank lines.",
            })

        # Check for very long lines
        long_lines = [i for i, l in enumerate(lines, 1) if len(l) > 200]
        if long_lines:
            issues.append({
                "level": "warning",
                "check": "text_line_length",
                "message": f"Lines exceeding 200 chars at line(s): {', '.join(str(l) for l in long_lines[:5])}",
            })

        return issues

    def _format_report(
        self,
        path: str,
        passed: bool,
        errors: List[Dict[str, str]],
        warnings: List[Dict[str, str]],
    ) -> str:
        status = "✅ PASS" if passed else "❌ FAIL"
        lines = [f"## Validation: {status} — {path}", ""]

        if errors:
            lines.append("### Errors")
            for e in errors:
                lines.append(f"- ❌ [{e['check']}] {e['message']}")
            lines.append("")

        if warnings:
            lines.append("### Warnings")
            for w in warnings:
                lines.append(f"- ⚠️ [{w['check']}] {w['message']}")
            lines.append("")

        if not errors and not warnings:
            lines.append("No issues found. Resume looks good!")

        return "\n".join(lines)

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return self.workspace_dir / p
