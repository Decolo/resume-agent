"""Compatibility checks for Slice F web UI asset extraction."""

from __future__ import annotations

import importlib
from pathlib import Path

api_app_module = importlib.import_module("apps.api.resume_agent_api.app")


def test_ui_dir_resolves_to_apps_web_assets() -> None:
    expected_ui_dir = (Path(__file__).resolve().parents[1] / "apps" / "web" / "ui").resolve()
    resolved_ui_dir = api_app_module._resolve_ui_dir().resolve()

    assert resolved_ui_dir == expected_ui_dir
    assert (resolved_ui_dir / "index.html").exists()
    assert (resolved_ui_dir / "app.js").exists()
    assert (resolved_ui_dir / "styles.css").exists()
