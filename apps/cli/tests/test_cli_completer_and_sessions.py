"""Tests for CLI completer and /sessions fuzzy filtering."""

from __future__ import annotations

import io

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from rich.console import Console

import apps.cli.resume_agent_cli.app as cli_app


class _FakeSessionManager:
    def __init__(self) -> None:
        self._sessions = [
            {
                "id": "session_20260223_090000_backend_engineer_abcd1234",
                "created_at": "2026-02-23T09:00:00",
                "updated_at": "2026-02-23T09:05:00",
                "mode": "single-agent",
                "message_count": 10,
                "total_tokens": 1234,
            },
            {
                "id": "session_20260220_090000_data_scientist_efgh5678",
                "created_at": "2026-02-20T09:00:00",
                "updated_at": "2026-02-20T09:05:00",
                "mode": "multi-agent",
                "message_count": 8,
                "total_tokens": 900,
            },
        ]

    def list_sessions(self) -> list[dict]:
        return list(self._sessions)


@pytest.mark.asyncio
async def test_sessions_command_supports_fuzzy_query(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)

    manager = _FakeSessionManager()
    assert await cli_app.handle_command("/sessions bkeng", object(), session_manager=manager)

    rendered = output.getvalue().lower()
    assert "backend_engineer" in rendered
    assert "data_scientist" not in rendered


@pytest.mark.asyncio
async def test_sessions_command_shows_no_match_message(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)

    manager = _FakeSessionManager()
    assert await cli_app.handle_command("/sessions zzz-not-found", object(), session_manager=manager)

    rendered = output.getvalue()
    assert "No sessions matched query: zzz-not-found" in rendered


def test_command_completer_suggests_command_prefix() -> None:
    completer = cli_app.ResumeCLICompleter()
    doc = Document(text="/st", cursor_position=3)

    completions = [item.text for item in completer.get_completions(doc, CompleteEvent(completion_requested=True))]
    assert "/stream" in completions


def test_command_completer_suggests_session_refs_for_load() -> None:
    manager = _FakeSessionManager()
    completer = cli_app.ResumeCLICompleter(session_manager=manager)
    doc = Document(text="/load ", cursor_position=6)

    completions = [item.text for item in completer.get_completions(doc, CompleteEvent(completion_requested=True))]
    assert "latest" in completions
    assert "1" in completions
    assert "session_20260223_090000_backend_engineer_abcd1234" in completions
