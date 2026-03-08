"""Guardrails for loop/tool responsibility boundary.

These tests prevent file mutation preview logic from drifting back into
`LLMAgent` core orchestration.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LLM_PATH = REPO_ROOT / "resume_agent" / "core" / "llm.py"


def _llmagent_class(tree: ast.AST) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "LLMAgent":
            return node
    raise AssertionError("LLMAgent class not found in resume_agent/core/llm.py")


def test_llmagent_does_not_directly_read_or_write_files() -> None:
    """LLMAgent should orchestrate tools, not do filesystem I/O itself."""
    tree = ast.parse(LLM_PATH.read_text(encoding="utf-8"), filename=str(LLM_PATH))
    llm_class = _llmagent_class(tree)

    forbidden_attr_calls = {"read_text", "write_text"}
    violations: list[str] = []

    for node in ast.walk(llm_class):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Attribute) and node.func.attr in forbidden_attr_calls:
            violations.append(f"line {node.lineno}: .{node.func.attr}(...)")

        if isinstance(node.func, ast.Name) and node.func.id == "open":
            violations.append(f"line {node.lineno}: open(...)")

    assert not violations, (
        "LLMAgent should not perform direct file I/O. "
        "Move file reads/writes to tool adapters.\n" + "\n".join(violations)
    )


def test_llmagent_does_not_compute_diffs_directly() -> None:
    """Diff construction for approval preview should be tool-owned."""
    tree = ast.parse(LLM_PATH.read_text(encoding="utf-8"), filename=str(LLM_PATH))
    llm_class = _llmagent_class(tree)

    violations: list[str] = []
    for node in ast.walk(llm_class):
        if not isinstance(node, ast.Call):
            continue
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "difflib"
            and node.func.attr == "unified_diff"
        ):
            violations.append(f"line {node.lineno}: difflib.unified_diff(...)")

    assert not violations, (
        "LLMAgent should not build unified diffs directly. "
        "Use tool build_approval_context hooks instead.\n" + "\n".join(violations)
    )
