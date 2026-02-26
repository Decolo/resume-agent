"""Architecture boundary tests for flattened package topology.

Enforces the dependency DAG:
  cli → core, tools, providers
  tools → domain, core
  core → domain, providers
  domain → (nothing)
  providers → (nothing)
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "resume_agent"

SUBMODULES = {"cli", "core", "domain", "providers", "tools"}

ALLOWED_DEPS: dict[str, set[str]] = {
    "cli": {"core", "tools", "providers"},
    "tools": {"domain", "core"},
    "core": {"domain", "providers"},
    "domain": set(),
    "providers": set(),
}


def _submodule_of(file_path: Path) -> str | None:
    rel = file_path.relative_to(SOURCE_ROOT)
    parts = rel.parts
    if parts and parts[0] in SUBMODULES:
        return parts[0]
    return None


def _imported_submodules(file_path: Path) -> set[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _extract(alias.name, result)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            _extract(node.module, result)
    return result


def _extract(module_name: str, out: set[str]) -> None:
    """If module_name is resume_agent.<sub>.*, add <sub> to out."""
    parts = module_name.split(".")
    if len(parts) >= 2 and parts[0] == "resume_agent" and parts[1] in SUBMODULES:
        out.add(parts[1])


def test_architecture_boundaries() -> None:
    violations: list[str] = []
    for py_file in sorted(SOURCE_ROOT.rglob("*.py")):
        owner = _submodule_of(py_file)
        if owner is None:
            continue
        for dep in _imported_submodules(py_file):
            if dep != owner and dep not in ALLOWED_DEPS.get(owner, set()):
                rel = py_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel}: resume_agent.{owner} imports resume_agent.{dep} "
                    f"(allowed: {sorted(ALLOWED_DEPS.get(owner, set()))})"
                )

    assert not violations, "Architecture boundary violation(s):\n" + "\n".join(sorted(violations))
