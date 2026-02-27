"""Guardrails ensuring no legacy flat-namespace imports remain."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "resume_agent"
TESTS_ROOT = REPO_ROOT / "tests"

LEGACY_NAMESPACES = {
    "resume_agent_core",
    "resume_agent_domain",
    "resume_agent_providers",
    "resume_agent_tools",
    "resume_agent_cli",
}


def _imported_modules(file_path: Path) -> set[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    return imported


def test_no_legacy_flat_namespace_imports() -> None:
    """No source or test file should import the old resume_agent_* packages."""
    violations: list[str] = []
    roots = [SOURCE_ROOT, TESTS_ROOT]
    for root in roots:
        if not root.exists():
            continue
        for py_file in sorted(root.rglob("*.py")):
            for mod in _imported_modules(py_file):
                if mod in LEGACY_NAMESPACES:
                    rel = py_file.relative_to(REPO_ROOT)
                    violations.append(f"{rel} imports legacy namespace {mod}")

    assert not violations, "Legacy namespace import(s) found:\n" + "\n".join(sorted(violations))


def test_old_monorepo_directories_are_gone() -> None:
    """The apps/ and packages/ directories should no longer exist."""
    assert not (REPO_ROOT / "apps").exists(), "apps/ directory still exists"
    assert not (REPO_ROOT / "packages").exists(), "packages/ directory still exists"
