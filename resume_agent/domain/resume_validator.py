"""Pure domain logic for resume content validation.

All functions operate on content strings -- no file I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ValidationResult:
    """Structured result from resume validation."""

    valid: bool
    errors: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[Dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_resume(content: str, file_format: str = ".md") -> ValidationResult:
    """Validate resume *content* for completeness and correctness.

    *file_format* should be the file extension (e.g. ``".html"``,
    ``".json"``, ``".md"``).  Returns a :class:`ValidationResult`.
    """
    issues: List[Dict[str, str]] = []

    issues.extend(_check_content(content))

    fmt = file_format.lower()
    if fmt == ".html":
        issues.extend(_check_html(content))
    elif fmt == ".json":
        issues.extend(_check_json(content))
    elif fmt in (".md", ".txt"):
        issues.extend(_check_text(content))

    errors = [i for i in issues if i["level"] == "error"]
    warnings = [i for i in issues if i["level"] == "warning"]

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_validation_report(path: str, result: ValidationResult) -> str:
    """Render a :class:`ValidationResult` as a human-readable report."""
    status = "PASS" if result.valid else "FAIL"
    lines = [f"## Validation: {status} -- {path}", ""]

    if result.errors:
        lines.append("### Errors")
        for e in result.errors:
            lines.append(f"- [{e['check']}] {e['message']}")
        lines.append("")

    if result.warnings:
        lines.append("### Warnings")
        for w in result.warnings:
            lines.append(f"- [{w['check']}] {w['message']}")
        lines.append("")

    if not result.errors and not result.warnings:
        lines.append("No issues found. Resume looks good!")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Private checks
# ---------------------------------------------------------------------------


def _check_content(content: str) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    if not content.strip():
        issues.append({"level": "error", "check": "empty", "message": "File is empty"})
        return issues

    word_count = len(content.split())
    if word_count < 50:
        issues.append(
            {
                "level": "error",
                "check": "length",
                "message": f"Resume is too short ({word_count} words). Minimum recommended: 150 words.",
            }
        )
    elif word_count < 150:
        issues.append(
            {
                "level": "warning",
                "check": "length",
                "message": f"Resume is short ({word_count} words). Recommended: 300-800 words.",
            }
        )
    elif word_count > 1500:
        issues.append(
            {
                "level": "warning",
                "check": "length",
                "message": f"Resume is long ({word_count} words). Consider trimming to 1-2 pages.",
            }
        )

    placeholders = re.findall(
        r"\b(?:TODO|FIXME|XXX|PLACEHOLDER|INSERT|YOUR NAME|COMPANY NAME)\b",
        content,
        re.IGNORECASE,
    )
    if placeholders:
        issues.append(
            {
                "level": "error",
                "check": "placeholders",
                "message": f"Contains placeholder text: {', '.join(set(placeholders))}",
            }
        )

    if "\ufffd" in content or "\u00e2\u20ac" in content or "\u00c3" in content:
        issues.append(
            {
                "level": "error",
                "check": "encoding",
                "message": "Contains encoding artifacts (mojibake). Re-save with UTF-8 encoding.",
            }
        )

    return issues


def _check_html(content: str) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    if "<html" not in content.lower():
        issues.append(
            {"level": "error", "check": "html_structure", "message": "Missing <html> tag -- not a valid HTML document."}
        )
    if "<head" not in content.lower():
        issues.append({"level": "warning", "check": "html_head", "message": "Missing <head> section."})
    if "charset" not in content.lower():
        issues.append(
            {
                "level": "warning",
                "check": "html_charset",
                "message": 'No charset declaration. Add <meta charset="UTF-8">.',
            }
        )
    if "<style" not in content.lower() and "stylesheet" not in content.lower():
        issues.append(
            {
                "level": "warning",
                "check": "html_styles",
                "message": "No CSS styles found. The resume may look unstyled.",
            }
        )

    return issues


def _check_json(content: str) -> List[Dict[str, str]]:
    import json as json_mod

    issues: List[Dict[str, str]] = []

    try:
        data = json_mod.loads(content)
    except json_mod.JSONDecodeError as e:
        issues.append({"level": "error", "check": "json_parse", "message": f"Invalid JSON: {e}"})
        return issues

    if not isinstance(data, dict):
        issues.append(
            {"level": "error", "check": "json_structure", "message": "JSON root must be an object, not an array."}
        )
        return issues

    if "basics" not in data:
        issues.append(
            {"level": "warning", "check": "json_schema", "message": "Missing 'basics' section (JSON Resume standard)."}
        )
    elif not data["basics"].get("name"):
        issues.append({"level": "warning", "check": "json_name", "message": "Missing name in basics section."})

    return issues


def _check_text(content: str) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    lines = content.strip().split("\n")
    if lines and not lines[0].strip():
        issues.append({"level": "warning", "check": "text_start", "message": "File starts with blank lines."})

    long_lines = [i for i, line in enumerate(lines, 1) if len(line) > 200]
    if long_lines:
        issues.append(
            {
                "level": "warning",
                "check": "text_line_length",
                "message": f"Lines exceeding 200 chars at line(s): {', '.join(str(ln) for ln in long_lines[:5])}",
            }
        )

    return issues
