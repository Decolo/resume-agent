"""Update resume sections via JSON path expressions.

Uses ``jsonpath-ng`` to locate and modify specific fields inside a
JSON Resume dict, so the web UI can make surgical edits without
rewriting the entire document.
"""

from __future__ import annotations

import json
from typing import Any

from jsonpath_ng import parse as jsonpath_parse
from resume_agent_core.tools.base import BaseTool, ToolResult


class UpdateSectionTool(BaseTool):
    """Apply a JSON-path update to a JSON Resume string."""

    name = "update_section"
    description = (
        "Update a specific section of a JSON Resume using a JSON path expression. "
        'Example paths: "$.basics.summary", "$.work[0].highlights[2]", '
        "\"$.skills[?name='Python'].level\"."
    )
    parameters = {
        "resume_json": {
            "type": "string",
            "description": "The full JSON Resume content as a string",
            "required": True,
        },
        "json_path": {
            "type": "string",
            "description": "JSON path expression targeting the field to update",
            "required": True,
        },
        "value": {
            "type": "string",
            "description": "New value (JSON-encoded for objects/arrays, plain string otherwise)",
            "required": True,
        },
    }

    async def execute(
        self,
        resume_json: str,
        json_path: str,
        value: str,
    ) -> ToolResult:
        try:
            data = json.loads(resume_json)
        except json.JSONDecodeError as exc:
            return ToolResult(success=False, output="", error=f"Invalid JSON input: {exc}")

        # Parse the value -- try JSON first, fall back to plain string
        parsed_value: Any
        try:
            parsed_value = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            parsed_value = value

        try:
            expr = jsonpath_parse(json_path)
        except Exception as exc:
            return ToolResult(success=False, output="", error=f"Invalid JSON path: {exc}")

        matches = expr.find(data)
        if not matches:
            return ToolResult(
                success=False,
                output="",
                error=f"No match found for path: {json_path}",
            )

        for match in matches:
            match.full_path.update(data, parsed_value)

        updated_json = json.dumps(data, indent=2, ensure_ascii=False)
        return ToolResult(
            success=True,
            output=f"Updated {len(matches)} match(es) at {json_path}",
            data={"updated_json": updated_json, "matches": len(matches)},
        )
