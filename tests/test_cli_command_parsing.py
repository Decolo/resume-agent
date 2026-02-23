"""CLI command parsing regression tests."""

from __future__ import annotations

import pytest

from apps.cli.resume_agent_cli.app import handle_command


class _FakeSessionManager:
    def __init__(self, session_id: str = "session_20260223_120000_deadbeef") -> None:
        self.session_id = session_id
        self.saved_name: str | None = None
        self.loaded_session_id: str | None = None
        self.restored = False

    def save_session(self, agent: object, session_name: str | None = None) -> str:
        self.saved_name = session_name
        return self.session_id

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
            "schema_version": "1.0",
            "session": {},
            "conversation": {"messages": []},
            "observability": {"events": []},
        }

    def restore_agent_state(self, agent: object, session_data: dict) -> None:
        self.restored = True


@pytest.mark.asyncio
async def test_save_command_preserves_custom_name_case_and_spacing() -> None:
    manager = _FakeSessionManager()

    assert await handle_command("/save My Session V1", object(), session_manager=manager)
    assert manager.saved_name == "My Session V1"


@pytest.mark.asyncio
async def test_load_command_preserves_session_id_case() -> None:
    session_id = "session_20260223_MyCase_deadbeef"
    manager = _FakeSessionManager(session_id=session_id)

    assert await handle_command(f"/load {session_id}", object(), session_manager=manager)
    assert manager.loaded_session_id == session_id
    assert manager.restored is True


@pytest.mark.asyncio
async def test_export_command_rejects_invalid_format_without_crashing() -> None:
    assert await handle_command("/export file yaml", object())
