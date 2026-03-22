"""Tests for CLI completer, /resume, and /compact behavior."""

from __future__ import annotations

import asyncio
import io
from types import SimpleNamespace

import pytest
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

import resume_agent.cli.app as cli_app
from resume_agent.core.llm import COMPRESSION_STATE_PREFIX, ContextBudgetSnapshot, HistoryManager
from resume_agent.providers.types import Message


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
                "mode": "single-agent",
                "message_count": 8,
                "total_tokens": 900,
            },
        ]
        self.loaded_session_id: str | None = None
        self.saved_session_id: str | None = None
        self.restored = False
        self.cleared = False

    def list_sessions(self) -> list[dict]:
        return list(self._sessions)

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

    def save_session(self, agent: object, session_id: str | None = None) -> str:
        self.saved_session_id = session_id or "session_20260224_090000_compacted_zzzz9999"
        return self.saved_session_id

    def clear_sessions(self) -> int:
        removed = len(self._sessions)
        self._sessions = []
        self.cleared = True
        return removed


class _FakePromptSession:
    def __init__(self, response: str) -> None:
        self.response = response

    async def prompt_async(self, prompt: str) -> str:
        return self.response


@pytest.mark.asyncio
async def test_resume_command_supports_fuzzy_query(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)

    manager = _FakeSessionManager()
    assert await cli_app.handle_command("/resume bkeng", object(), session_manager=manager)

    assert manager.loaded_session_id == "session_20260223_090000_backend_engineer_abcd1234"
    assert manager.restored is True


@pytest.mark.asyncio
async def test_resume_command_uses_picker_and_loads_selected_session() -> None:
    manager = _FakeSessionManager()

    with create_pipe_input() as pipe_input:
        prompt_session = PromptSession(input=pipe_input, output=DummyOutput())
        command_task = asyncio.create_task(
            cli_app.handle_command("/resume", object(), session_manager=manager, prompt_session=prompt_session)
        )
        await asyncio.sleep(0.05)
        pipe_input.send_text("\x1b[B")  # Move to first item.
        pipe_input.send_text("\x1b[B")  # Move to second item.
        pipe_input.send_text("\r")  # Confirm selection.
        assert await command_task

    assert manager.loaded_session_id == "session_20260220_090000_data_scientist_efgh5678"
    assert manager.restored is True


@pytest.mark.asyncio
async def test_resume_command_cancelled_picker_does_not_load(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)

    manager = _FakeSessionManager()

    with create_pipe_input() as pipe_input:
        prompt_session = PromptSession(input=pipe_input, output=DummyOutput())
        command_task = asyncio.create_task(
            cli_app.handle_command("/resume", object(), session_manager=manager, prompt_session=prompt_session)
        )
        await asyncio.sleep(0.05)
        pipe_input.send_text("\r")  # No explicit selection -> cancel.
        assert await command_task

    assert manager.loaded_session_id is None
    assert manager.restored is False
    assert "Session selection cancelled." in output.getvalue()


@pytest.mark.asyncio
async def test_resume_command_shows_no_match_message(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)

    manager = _FakeSessionManager()
    assert await cli_app.handle_command("/resume zzz-not-found", object(), session_manager=manager)

    rendered = output.getvalue()
    assert "No sessions matched query: zzz-not-found" in rendered


@pytest.mark.asyncio
async def test_select_session_id_returns_dropdown_selection() -> None:
    manager = _FakeSessionManager()
    with create_pipe_input() as pipe_input:
        prompt_session = PromptSession(input=pipe_input, output=DummyOutput())
        select_task = asyncio.create_task(
            cli_app._select_session_id(
                manager.list_sessions(),
                session_query="",
                prompt_session=prompt_session,
            )
        )
        await asyncio.sleep(0.05)
        pipe_input.send_text("\x1b[B")
        pipe_input.send_text("\x1b[B")
        pipe_input.send_text("\r")
        selected = await select_task

    assert selected == "session_20260220_090000_data_scientist_efgh5678"


@pytest.mark.asyncio
async def test_select_session_id_none_when_dropdown_cancelled() -> None:
    manager = _FakeSessionManager()
    with create_pipe_input() as pipe_input:
        prompt_session = PromptSession(input=pipe_input, output=DummyOutput())
        select_task = asyncio.create_task(
            cli_app._select_session_id(
                manager.list_sessions(),
                session_query="",
                prompt_session=prompt_session,
            )
        )
        await asyncio.sleep(0.05)
        pipe_input.send_text("\r")
        selected = await select_task

    assert selected is None


@pytest.mark.asyncio
async def test_select_session_id_falls_back_when_dropdown_errors(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)

    manager = _FakeSessionManager()

    async def _raise_dropdown(prompt_session, completer, session_query, option_count):  # type: ignore[no-untyped-def]
        raise RuntimeError("no tty")

    monkeypatch.setattr(cli_app, "_prompt_session_dropdown_input", _raise_dropdown)

    selected = await cli_app._select_session_id(
        manager.list_sessions(),
        session_query="",
        prompt_session=_FakePromptSession("1"),
        verbose=True,
    )

    assert selected == "session_20260223_090000_backend_engineer_abcd1234"
    rendered = output.getvalue()
    assert "Inline session picker failed; falling back to numeric selection." in rendered
    assert "Please report this issue if it keeps happening." in rendered
    assert "Picker error: RuntimeError: no tty" in rendered


@pytest.mark.asyncio
async def test_resume_single_match_requires_explicit_interactive_selection(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)

    manager = _FakeSessionManager()
    with create_pipe_input() as pipe_input:
        prompt_session = PromptSession(input=pipe_input, output=DummyOutput())
        command_task = asyncio.create_task(
            cli_app.handle_command("/resume bkeng", object(), session_manager=manager, prompt_session=prompt_session)
        )
        await asyncio.sleep(0.05)
        pipe_input.send_text("\r")  # One match still needs explicit selection in interactive mode.
        assert await command_task

    assert manager.loaded_session_id is None
    assert "Session selection cancelled." in output.getvalue()


@pytest.mark.asyncio
async def test_resume_single_match_loads_after_explicit_selection(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)

    manager = _FakeSessionManager()
    with create_pipe_input() as pipe_input:
        prompt_session = PromptSession(input=pipe_input, output=DummyOutput())
        command_task = asyncio.create_task(
            cli_app.handle_command("/resume bkeng", object(), session_manager=manager, prompt_session=prompt_session)
        )
        await asyncio.sleep(0.05)
        pipe_input.send_text("\x1b[B")  # Select the only option.
        pipe_input.send_text("\r")
        assert await command_task

    assert manager.loaded_session_id == "session_20260223_090000_backend_engineer_abcd1234"
    assert manager.restored is True


@pytest.mark.asyncio
async def test_fallback_picker_accepts_numeric_selection(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)

    selected = await cli_app._fallback_pick_session_id(
        [("id-1", "1. first"), ("id-2", "2. second")],
        prompt_session=_FakePromptSession("2"),
    )

    assert selected == "id-2"


@pytest.mark.asyncio
async def test_fallback_picker_rejects_invalid_selection(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)

    selected = await cli_app._fallback_pick_session_id(
        [("id-1", "1. first"), ("id-2", "2. second")],
        prompt_session=_FakePromptSession("invalid"),
    )

    assert selected is None
    assert "Invalid selection." in output.getvalue()


@pytest.mark.asyncio
async def test_fallback_picker_empty_selection_cancels(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)

    selected = await cli_app._fallback_pick_session_id(
        [("id-1", "1. first"), ("id-2", "2. second")],
        prompt_session=_FakePromptSession(""),
    )

    assert selected is None


def test_restore_loaded_session_renders_history(monkeypatch) -> None:
    manager = _FakeSessionManager()
    sessions = manager.list_sessions()
    rendered = {"history": False, "context": False}

    def _fake_render_loaded_history(agent, max_rows=8):  # type: ignore[no-untyped-def]
        rendered["history"] = True

    def _fake_render_context_status(agent):  # type: ignore[no-untyped-def]
        rendered["context"] = True

    monkeypatch.setattr(cli_app, "_render_loaded_history", _fake_render_loaded_history)
    monkeypatch.setattr(cli_app, "_render_context_status", _fake_render_context_status)
    cli_app._restore_loaded_session(sessions[0]["id"], sessions, manager, object())

    assert rendered["history"] is True
    assert rendered["context"] is True


def test_render_loaded_history_keeps_compaction_summary_visible(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)

    manager = HistoryManager()
    manager.restore_compaction_state(
        {
            "history_format": "turn_tree_v1",
            "turns": [],
            "compression_state": {
                "covered_messages": 9,
                "summary_chunks": ["Earlier edits"],
            },
            "compaction_checkpoints": [
                {
                    "checkpoint_id": 1,
                    "covered_messages": 9,
                    "compacted_messages": 9,
                    "summary_text": "Earlier edits",
                }
            ],
        }
    )
    manager._history = [Message.assistant(f"{COMPRESSION_STATE_PREFIX}\ncovered_messages=9")] + [
        Message.user(f"msg {i}") for i in range(1, 11)
    ]
    llm_agent = SimpleNamespace(history_manager=manager)
    monkeypatch.setattr(cli_app, "_get_llm_agents", lambda agent: [llm_agent])

    cli_app._render_compaction_status(object())
    cli_app._render_loaded_history(object(), max_rows=4)

    rendered = output.getvalue()
    assert "covered_messages: 9" in rendered
    assert COMPRESSION_STATE_PREFIX in rendered
    assert "Showing compaction summary plus last 3 of 11 messages." in rendered


@pytest.mark.asyncio
async def test_compact_command_compacts_and_persists_session(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)

    manager = HistoryManager()
    llm_agent = SimpleNamespace(current_session_id="session_existing", history_manager=manager)

    async def _compact_history(*, force: bool = False) -> bool:
        assert force is True
        manager.restore_compaction_state(
            {
                "history_format": "turn_tree_v1",
                "turns": [],
                "compression_state": {
                    "covered_messages": 7,
                    "summary_chunks": ["Earlier edits"],
                },
                "compaction_checkpoints": [
                    {
                        "checkpoint_id": 1,
                        "covered_messages": 7,
                        "compacted_messages": 7,
                        "summary_text": "Earlier edits",
                    }
                ],
            }
        )
        manager._history = [
            Message.assistant(f"{COMPRESSION_STATE_PREFIX}\ncovered_messages=7"),
            Message.user("latest"),
        ]
        return True

    llm_agent.compact_history = _compact_history
    monkeypatch.setattr(cli_app, "_get_llm_agents", lambda agent: [llm_agent])

    session_manager = _FakeSessionManager()
    assert await cli_app.handle_command("/compact", object(), session_manager=session_manager)

    rendered = output.getvalue()
    assert "History compaction complete" in rendered
    assert "covered_messages=7" in rendered
    assert "Session updated: session_existing" in rendered
    assert session_manager.saved_session_id == "session_existing"


@pytest.mark.asyncio
async def test_context_command_renders_budget_panel(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)

    llm_agent = SimpleNamespace(
        get_context_budget_snapshot=lambda: ContextBudgetSnapshot(
            provider="gemini",
            model="gemini-2.5-pro",
            source="api",
            context_window=1_048_576,
            estimated_prompt_tokens=12_345,
            reserved_output_tokens=2_048,
            estimated_remaining_context=1_034_183,
            usage_percent=1.2,
        )
    )
    monkeypatch.setattr(cli_app, "_get_llm_agents", lambda agent: [llm_agent])

    assert await cli_app.handle_command("/context", object())

    rendered = output.getvalue()
    assert "Context State" in rendered
    assert "context_window: 1,048,576" in rendered
    assert "estimated_remaining_context: 1,034,183" in rendered


@pytest.mark.asyncio
async def test_context_command_reports_unavailable_budget(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)
    monkeypatch.setattr(cli_app, "_get_llm_agents", lambda agent: [])

    assert await cli_app.handle_command("/context", object())

    rendered = output.getvalue()
    assert "Context budget unavailable for the current session." in rendered


def test_build_context_rprompt_formats_remaining_context(monkeypatch) -> None:
    llm_agent = SimpleNamespace(
        get_context_budget_snapshot=lambda: ContextBudgetSnapshot(
            provider="gemini",
            model="gemini-2.5-pro",
            source="api",
            context_window=1_048_576,
            estimated_prompt_tokens=12_345,
            reserved_output_tokens=2_048,
            estimated_remaining_context=1_034_183,
            usage_percent=1.2,
        )
    )
    monkeypatch.setattr(cli_app, "_get_llm_agents", lambda agent: [llm_agent])

    assert cli_app._build_context_rprompt(object()) == "ctx 1.03M left"


def test_build_context_rprompt_hides_unknown_remaining_context(monkeypatch) -> None:
    llm_agent = SimpleNamespace(
        get_context_budget_snapshot=lambda: ContextBudgetSnapshot(
            provider="openai",
            model="unknown",
            source="unknown",
            context_window=None,
            estimated_prompt_tokens=3_000,
            reserved_output_tokens=2_048,
            estimated_remaining_context=None,
            usage_percent=None,
        )
    )
    monkeypatch.setattr(cli_app, "_get_llm_agents", lambda agent: [llm_agent])

    assert cli_app._build_context_rprompt(object()) is None


@pytest.mark.asyncio
async def test_run_interactive_passes_context_rprompt_to_prompt_session(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)
    monkeypatch.setattr(cli_app, "print_banner", lambda: None)

    captured: dict[str, object] = {}

    class _FakePromptSession:
        def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            captured["init_kwargs"] = kwargs

        def prompt(self, message: str, **kwargs) -> str:  # type: ignore[no-untyped-def]
            captured["message"] = message
            captured["rprompt"] = kwargs.get("rprompt")
            return "/exit"

    async def _fake_handle_command(*args, **kwargs) -> bool:  # type: ignore[no-untyped-def]
        captured["command"] = args[0]
        return False

    llm_agent = SimpleNamespace(
        get_context_budget_snapshot=lambda: ContextBudgetSnapshot(
            provider="gemini",
            model="gemini-2.5-pro",
            source="api",
            context_window=1_048_576,
            estimated_prompt_tokens=12_345,
            reserved_output_tokens=2_048,
            estimated_remaining_context=1_034_183,
            usage_percent=1.2,
        )
    )

    monkeypatch.setattr(cli_app, "PromptSession", _FakePromptSession)
    monkeypatch.setattr(cli_app, "handle_command", _fake_handle_command)
    monkeypatch.setattr(cli_app, "_get_llm_agents", lambda agent: [llm_agent])

    await cli_app.run_interactive(object())

    assert captured["message"] == "\n📝 You: "
    assert captured["rprompt"] == "ctx 1.03M left"
    assert captured["command"] == "/exit"


@pytest.mark.asyncio
async def test_clear_sessions_command_removes_all_saved_sessions(monkeypatch) -> None:
    output = io.StringIO()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)

    session_manager = _FakeSessionManager()
    llm_agent = SimpleNamespace(current_session_id="session_existing")
    monkeypatch.setattr(cli_app, "_get_llm_agents", lambda agent: [llm_agent])

    assert await cli_app.handle_command("/clear-sessions", object(), session_manager=session_manager)

    rendered = output.getvalue()
    assert "Cleared 2 saved session(s)." in rendered
    assert session_manager.cleared is True
    assert llm_agent.current_session_id is None


def test_command_completer_suggests_command_prefix() -> None:
    completer = cli_app.ResumeCLICompleter()
    doc = Document(text="/st", cursor_position=3)

    completions = [item.text for item in completer.get_completions(doc, CompleteEvent(completion_requested=True))]
    assert "/stream" in completions
    assert "/resume" in cli_app.ResumeCLICompleter.COMMANDS
    assert "/compact" in cli_app.ResumeCLICompleter.COMMANDS
    assert "/context" in cli_app.ResumeCLICompleter.COMMANDS
    assert "/clear-sessions" in cli_app.ResumeCLICompleter.COMMANDS


def test_command_completer_suggests_session_refs_for_delete() -> None:
    manager = _FakeSessionManager()
    completer = cli_app.ResumeCLICompleter(session_manager=manager)
    doc = Document(text="/delete-session ", cursor_position=16)

    completions = [item.text for item in completer.get_completions(doc, CompleteEvent(completion_requested=True))]
    assert "latest" not in completions
    assert "1" in completions
    assert "session_20260223_090000_backend_engineer_abcd1234" in completions


def test_file_list_result_summary_is_single_line() -> None:
    output = "file\t1522\tsample_resume.md\n" "dir\t0\tsessions\n"
    rendered = cli_app._summarize_tool_result("file_list", output)

    assert rendered == "2 entries: sample_resume.md, sessions/"


def test_tool_call_inline_format_is_single_line() -> None:
    line = cli_app._format_tool_call_inline("file_list", {"path": ".", "recursive": False})
    assert line.startswith("🔧 file_list(")
    assert "path=." in line
    assert "recursive=False" in line


def test_tool_result_summary_truncates_multiline_output() -> None:
    rendered = cli_app._summarize_tool_result("bash", "line1\nline2\nline3")
    assert rendered == "line1 (+2 lines)"


def test_parse_approval_choice_does_not_escalate_reject_all() -> None:
    assert cli_app._parse_approval_choice("reject all") == "reject"
    assert cli_app._parse_approval_choice("3 reject all") == "reject"


def test_parse_approval_choice_handles_common_inputs() -> None:
    assert cli_app._parse_approval_choice("[1] Approve") == "approve"
    assert cli_app._parse_approval_choice("2") == "approve_all"
    assert cli_app._parse_approval_choice("approve all") == "approve_all"
