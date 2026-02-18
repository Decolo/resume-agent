"""Global pytest fixtures for deterministic test environment."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear local runtime env that can leak into tests on developer machines."""
    for key in (
        "RESUME_AGENT_EXECUTOR_MODE",
        "RESUME_AGENT_DEFAULT_PROVIDER",
        "RESUME_AGENT_DEFAULT_MODEL",
        "RESUME_AGENT_API_BASE",
        "RESUME_AGENT_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
