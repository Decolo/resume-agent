"""Guardrails for CI workflow stability.

These tests prevent accidental drift in required CI jobs/check names.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _load_ci_workflow() -> dict:
    return yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_ci_required_jobs_exist() -> None:
    workflow = _load_ci_workflow()
    jobs = workflow.get("jobs", {})
    assert {"test", "lint", "typecheck"} <= set(jobs.keys())


def test_ci_required_job_display_names_are_stable() -> None:
    workflow = _load_ci_workflow()
    jobs = workflow.get("jobs", {})
    expected = {
        "test": "test (py3.11)",
        "lint": "lint (ruff)",
        "typecheck": "typecheck (mypy)",
    }

    for job_id, display_name in expected.items():
        actual_name = jobs.get(job_id, {}).get("name")
        assert (
            actual_name == display_name
        ), f"{job_id} name changed from protected-check baseline; update branch protection if intentional"


def test_ci_required_job_commands_present() -> None:
    workflow = _load_ci_workflow()
    jobs = workflow.get("jobs", {})

    expected_run_fragments = {
        "test": "uv run --extra dev pytest -q",
        "lint": "uv run --extra dev ruff check .",
        "typecheck": "uv run --extra dev mypy",
    }

    for job_id, command_fragment in expected_run_fragments.items():
        steps = jobs.get(job_id, {}).get("steps", [])
        run_commands = [step.get("run", "") for step in steps if isinstance(step, dict)]
        assert any(
            command_fragment in command for command in run_commands
        ), f"{job_id} does not run expected command: {command_fragment}"
