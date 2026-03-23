"""CLI command parsing regression tests."""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from resume_agent.cli.app import handle_command


class _FakeSessionManager:
    def __init__(self, session_id: str = "session_20260223_120000_deadbeef") -> None:
        self.session_id = session_id
        self.loaded_session_id: str | None = None
        self.restored = False

    def list_sessions(self) -> list[dict]:
        return [
            {
                "id": self.session_id,
                "created_at": "2026-02-23T11:00:00",
                "updated_at": "2026-02-23T12:00:00",
                "mode": "single-agent",
                "message_count": 3,
                "total_tokens": 123,
            }
        ]

    def load_session(self, session_id: str) -> dict:
        self.loaded_session_id = session_id
        return {
            "schema_version": "2.0",
            "session": {},
            "conversation": {"history_format": "turn_tree_v1", "turns": []},
            "observability": {"events": []},
        }

    def restore_agent_state(self, agent: object, session_data: dict) -> None:
        self.restored = True


@pytest.mark.asyncio
async def test_unknown_load_command_does_not_attempt_session_restore(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr("resume_agent.cli.app.console", test_console)

    session_id = "session_20260223_MyCase_deadbeef"
    manager = _FakeSessionManager(session_id=session_id)

    assert await handle_command(f"/load {session_id}", object(), session_manager=manager)
    assert manager.loaded_session_id is None
    assert manager.restored is False
    assert "Unknown command: /load" in output.getvalue()


@pytest.mark.asyncio
async def test_unknown_sessions_command_does_not_attempt_session_restore(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr("resume_agent.cli.app.console", test_console)

    manager = _FakeSessionManager()

    assert await handle_command("/sessions", object(), session_manager=manager)
    assert manager.loaded_session_id is None
    assert manager.restored is False
    assert "Unknown command: /sessions" in output.getvalue()


@pytest.mark.asyncio
async def test_unknown_stream_command_is_reported(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr("resume_agent.cli.app.console", test_console)

    assert await handle_command("/stream status", object())
    assert "Unknown command: /stream status" in output.getvalue()


@pytest.mark.asyncio
async def test_export_command_rejects_unsupported_format_without_crashing() -> None:
    assert await handle_command("/export file yaml", object())
