"""Guardrails for packaging configuration during monorepo migration."""

from __future__ import annotations

from pathlib import Path

import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"


def _load_pyproject() -> dict:
    return tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))


def test_wheel_includes_monorepo_namespaces() -> None:
    pyproject = _load_pyproject()
    wheel_cfg = pyproject.get("tool", {}).get("hatch", {}).get("build", {}).get("targets", {}).get("wheel", {})
    packages = set(wheel_cfg.get("packages", []))
    assert {"resume_agent", "apps", "packages"} <= packages


def test_cli_entrypoint_remains_stable() -> None:
    pyproject = _load_pyproject()
    scripts = pyproject.get("project", {}).get("scripts", {})
    assert scripts.get("resume-agent") == "resume_agent.cli:main"
