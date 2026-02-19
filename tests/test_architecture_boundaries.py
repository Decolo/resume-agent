"""Architecture boundary tests for monorepo final topology."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
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

    for file_path in py_files:
        module = _module_name(file_path)
        imports = _imported_modules(file_path, module)

        for imported in imports:
            if imported.startswith("resume_agent"):
                violations.append(f"{module} imports {imported}; implementation must live under apps/* or packages/*")

        if module.startswith("packages."):
            for imported in imports:
                if imported.startswith("apps."):
                    violations.append(f"{module} imports {imported}; packages layer must not depend on apps layer")

        if module.startswith("packages.providers"):
            for imported in imports:
                if imported.startswith(("packages.core", "apps.")):
                    violations.append(
                        f"{module} imports {imported}; providers must remain isolated from core/app layers"
                    )

        if module.startswith("packages.contracts"):
            for imported in imports:
                if imported.startswith(("packages.core", "packages.providers", "apps.")):
                    violations.append(f"{module} imports {imported}; contracts must be app/core agnostic")

        if module.startswith("apps.api"):
            for imported in imports:
                if imported.startswith("apps.cli"):
                    violations.append(f"{module} imports {imported}; api app must not depend on cli app")

        if module.startswith("apps.cli"):
            for imported in imports:
                if imported.startswith("apps.api"):
                    violations.append(f"{module} imports {imported}; cli app must not depend on api app")

    assert not violations, "Architecture boundary violation(s):\n" + "\n".join(sorted(violations))
