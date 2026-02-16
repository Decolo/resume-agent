"""Compatibility checks for Slice E CLI app extraction."""

from __future__ import annotations

import resume_agent.cli as legacy_cli
from apps.cli.resume_agent_cli import app as package_cli


def test_cli_exports_are_compatible_with_new_source() -> None:
    assert legacy_cli.main is package_cli.main
    assert legacy_cli.handle_command is package_cli.handle_command
    assert legacy_cli.run_interactive is package_cli.run_interactive
