"""CLI stream-command removal regression tests."""

from __future__ import annotations

import io

import pytest
from rich.console import Console

import resume_agent.cli.app as cli_app
from resume_agent.cli.app import handle_command


@pytest.mark.asyncio
async def test_stream_command_is_unknown_after_default_live_rollout(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)

    assert await handle_command("/stream on", object())
    assert "Unknown command: /stream on" in output.getvalue()
