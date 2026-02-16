"""Guardrails enforcing legacy shim retirement."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    REPO_ROOT / "apps",
    REPO_ROOT / "packages",
)
LEGACY_PACKAGE_ROOT = REPO_ROOT / "resume_agent"


def _imported_modules(file_path: Path) -> set[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module)
    return imported


def test_apps_and_packages_do_not_import_legacy_resume_agent_namespace() -> None:
    violations: list[str] = []
    py_files: list[Path] = []
    for root in SOURCE_ROOTS:
        if root.exists():
            py_files.extend(sorted(root.rglob("*.py")))

    for file_path in py_files:
        module = ".".join(file_path.relative_to(REPO_ROOT).with_suffix("").parts)
        for imported in _imported_modules(file_path):
            if imported == "resume_agent" or imported.startswith("resume_agent."):
                violations.append(f"{module} imports {imported}")

    assert not violations, "Legacy namespace import violation(s):\n" + "\n".join(sorted(violations))


def test_legacy_resume_agent_package_is_reduced_to_minimal_shell() -> None:
    py_files = sorted(LEGACY_PACKAGE_ROOT.rglob("*.py"))
    relative = {str(path.relative_to(REPO_ROOT)) for path in py_files}
    assert relative == {"resume_agent/__init__.py"}
