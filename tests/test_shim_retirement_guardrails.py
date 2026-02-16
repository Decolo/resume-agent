"""Guardrails to prevent new shim dependencies in monorepo source paths."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    REPO_ROOT / "apps",
    REPO_ROOT / "packages",
)
SHIM_PREFIXES = (
    "resume_agent.agent",
    "resume_agent.agent_factory",
    "resume_agent.cache",
    "resume_agent.cli",
    "resume_agent.contracts",
    "resume_agent.llm",
    "resume_agent.observability",
    "resume_agent.preview",
    "resume_agent.providers",
    "resume_agent.retry",
    "resume_agent.session",
    "resume_agent.web.app",
)


def _module_name(file_path: Path) -> str:
    relative = file_path.relative_to(REPO_ROOT).with_suffix("")
    return ".".join(relative.parts)


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


def _is_shim_import(imported: str) -> bool:
    for shim in SHIM_PREFIXES:
        if imported == shim or imported.startswith(f"{shim}."):
            return True
    return False


def test_apps_and_packages_do_not_import_compatibility_shims() -> None:
    violations: list[str] = []
    py_files: list[Path] = []
    for root in SOURCE_ROOTS:
        if root.exists():
            py_files.extend(sorted(root.rglob("*.py")))

    for file_path in py_files:
        module = _module_name(file_path)
        for imported in _imported_modules(file_path):
            if _is_shim_import(imported):
                violations.append(f"{module} imports {imported}")

    assert not violations, "Compatibility shim import violation(s):\n" + "\n".join(sorted(violations))
