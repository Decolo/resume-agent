"""Architecture boundary tests.

These tests enforce dependency direction mechanically so drift is caught in CI.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    REPO_ROOT / "resume_agent",
    REPO_ROOT / "packages",
    REPO_ROOT / "apps",
)


def _module_name(file_path: Path) -> str:
    relative = file_path.relative_to(REPO_ROOT).with_suffix("")
    return ".".join(relative.parts)


def _imported_modules(file_path: Path, current_module: str) -> set[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    imported: set[str] = set()
    package_parts = current_module.split(".")[:-1]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
            continue

        if not isinstance(node, ast.ImportFrom):
            continue

        if node.level == 0:
            if node.module:
                imported.add(node.module)
            continue

        # Relative import resolution:
        # level=1 means current package, level=2 means parent package, etc.
        ascend = max(node.level - 1, 0)
        if ascend > len(package_parts):
            continue

        base_parts = package_parts[: len(package_parts) - ascend]
        if node.module:
            base_parts.extend(node.module.split("."))

        if base_parts:
            imported.add(".".join(base_parts))

    return imported


def test_architecture_boundaries() -> None:
    violations: list[str] = []
    py_files: list[Path] = []
    for root in SOURCE_ROOTS:
        if root.exists():
            py_files.extend(sorted(root.rglob("*.py")))

    provider_forbidden_prefixes = (
        "resume_agent.agents",
        "resume_agent.tools",
        "resume_agent.web",
        "resume_agent.cli",
        "resume_agent.agent",
        "resume_agent.agent_factory",
    )

    for file_path in py_files:
        module = _module_name(file_path)
        imports = _imported_modules(file_path, module)

        if not module.startswith("resume_agent.web"):
            for imported in imports:
                if imported.startswith("resume_agent.web"):
                    violations.append(f"{module} imports {imported}; only web package may depend on web adapters")

        if module.startswith("resume_agent.providers"):
            for imported in imports:
                if imported.startswith(provider_forbidden_prefixes):
                    violations.append(
                        f"{module} imports {imported}; providers must stay isolated from app/web/tool layers"
                    )

        if module.startswith("packages."):
            for imported in imports:
                if imported.startswith("apps."):
                    violations.append(f"{module} imports {imported}; packages layer must not depend on apps layer")

    assert not violations, "Architecture boundary violation(s):\n" + "\n".join(sorted(violations))
