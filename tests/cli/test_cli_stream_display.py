"""Behavior tests for interactive live stream display UX."""

from __future__ import annotations

import asyncio
import io

import pytest
from rich.console import Console

import resume_agent.cli.app as cli_app
import resume_agent.cli.stream_display as stream_display
from resume_agent.cli.stream_display import InteractiveTurnRenderer
from resume_agent.core.wire.types import StepBegin, TextDelta, ToolCallEvent, ToolResultEvent, TurnEnd


class _FakeLive:
    instances: list["_FakeLive"] = []

    def __init__(self, renderable, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.renderable = renderable
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        self.updates: list[object] = []
        _FakeLive.instances.append(self)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def update(self, renderable, refresh: bool = False) -> None:  # type: ignore[no-untyped-def]
        self.renderable = renderable
        self.updates.append((renderable, refresh))


def _renderable_to_text(renderable: object, *, width: int = 120) -> str:
    output = io.StringIO()
    console = Console(file=output, force_terminal=False, color_system=None, width=width)
    console.print(renderable)
    return output.getvalue()


def test_interactive_turn_renderer_updates_live_view_and_renders_stable_transcript(monkeypatch) -> None:
    output = io.StringIO()
    _FakeLive.instances.clear()
    monkeypatch.setattr(stream_display, "Live", _FakeLive)
    renderer = InteractiveTurnRenderer(Console(file=output, force_terminal=False, color_system=None, width=100))
    renderer.start()

    renderer.on_step_begin(1)
    renderer.on_tool_call("resume_parse", {"path": "examples/sample_resumes/sample_resume.md"})
    renderer.on_tool_result("resume_parse", "Parsed 1 resume file successfully.", True)
    renderer.on_text_delta("I reviewed your resume and found two gaps. Focus on ")
    renderer.on_text_delta("measurable impact.\nAdd metrics for your backend projects.")
    renderer.finish(
        "I reviewed your resume and found two gaps. Focus on measurable impact.\nAdd metrics for your backend projects."
    )

    rendered = output.getvalue()
    assert len(_FakeLive.instances) == 1
    assert _FakeLive.instances[0].started is True
    assert len(_FakeLive.instances[0].updates) >= 4
    refresh_flags = [refresh for _renderable, refresh in _FakeLive.instances[0].updates]
    assert True in refresh_flags
    assert False in refresh_flags
    assert "· Step 1" in rendered
    assert "resume_parse" in rendered
    assert "🤖 Assistant" in rendered
    assert "I reviewed your resume and found two gaps. Focus on measurable impact." in rendered


def test_interactive_turn_renderer_uses_final_text_when_no_stream_text(monkeypatch) -> None:
    output = io.StringIO()
    _FakeLive.instances.clear()
    monkeypatch.setattr(stream_display, "Live", _FakeLive)
    renderer = InteractiveTurnRenderer(Console(file=output, force_terminal=False, color_system=None, width=100))
    renderer.start()

    renderer.on_step_begin(1)
    renderer.on_tool_call("resume_parse", {"path": "examples/sample_resumes/sample_resume.md"})
    renderer.on_tool_result("resume_parse", "Parsed 1 resume file successfully.", True)
    renderer.finish("Final answer")

    rendered = output.getvalue()
    assert "resume_parse" in rendered
    assert "🤖 Assistant" in rendered
    assert "Final answer" in rendered


def test_interactive_turn_renderer_shows_live_status_and_clips_old_assistant_text(monkeypatch) -> None:
    output = io.StringIO()
    _FakeLive.instances.clear()
    monkeypatch.setattr(stream_display, "Live", _FakeLive)
    renderer = InteractiveTurnRenderer(Console(file=output, force_terminal=False, color_system=None, width=120))
    renderer.start()

    renderer.on_step_begin(2)
    renderer.on_tool_call("file_read", {"path": "sample_resume.md"})
    tool_live_text = _renderable_to_text(_FakeLive.instances[0].renderable, width=120)
    assert "Running file_read" in tool_live_text
    assert "Step 2" in tool_live_text

    renderer.on_tool_result("file_read", "# John Doe", True)
    renderer.on_text_delta("VERY-OLD-PREFIX " + ("OLD-SECTION " * 200))
    renderer.on_text_delta("LATEST-SENTENCE: emphasize scale, reliability, and migration ownership.")
    response_live_text = _renderable_to_text(_FakeLive.instances[0].renderable, width=120)
    normalized_live_text = " ".join(response_live_text.split())
    assert "Writing response" in response_live_text
    assert "LATEST-SENTENCE: emphasize scale, reliability, and migration ownership." in normalized_live_text
    assert "VERY-OLD-PREFIX" not in response_live_text


@pytest.mark.asyncio
async def test_run_interactive_real_case_live_transcript_renders_single_final_copy(monkeypatch) -> None:
    output = io.StringIO()
    _FakeLive.instances.clear()
    test_console = Console(file=output, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(cli_app, "console", test_console)
    monkeypatch.setattr(cli_app, "print_banner", lambda: None)
    monkeypatch.setattr(cli_app.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(stream_display, "Live", _FakeLive)

    class _FakePromptSession:
        def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            self._responses = iter(
                [
                    "Please tighten my backend engineer resume summary for a senior role.",
                    "/exit",
                ]
            )

        def prompt(self, message: str, **kwargs) -> str:  # type: ignore[no-untyped-def]
            return next(self._responses)

    class _FakeAgent:
        async def run(self, user_input: str, stream: bool = False, wire=None, **kwargs) -> str:  # type: ignore[no-untyped-def]
            assert "backend engineer resume summary" in user_input
            assert stream is True
            final_text = (
                "I tightened your summary around backend ownership and measurable impact.\n"
                "Lead with scale, reliability, and cross-team delivery."
            )
            wire.soul_side.send(StepBegin(n=1))
            await asyncio.sleep(0)
            wire.soul_side.send(
                ToolCallEvent(
                    name="resume_parse",
                    arguments={"path": "examples/sample_resumes/sample_resume.md"},
                )
            )
            await asyncio.sleep(0)
            wire.soul_side.send(
                ToolResultEvent(
                    name="resume_parse",
                    result="Parsed sample_resume.md successfully.",
                    success=True,
                )
            )
            await asyncio.sleep(0)
            wire.soul_side.send(
                TextDelta(text="I tightened your summary around backend ownership and measurable impact.\n")
            )
            await asyncio.sleep(0)
            wire.soul_side.send(TextDelta(text="Lead with scale, reliability, and cross-team delivery."))
            await asyncio.sleep(0)
            wire.soul_side.send(TurnEnd(final_text=final_text))
            return final_text

    monkeypatch.setattr(cli_app, "PromptSession", _FakePromptSession)

    await cli_app.run_interactive(_FakeAgent())

    rendered = output.getvalue()
    assert len(_FakeLive.instances) == 1
    assert _FakeLive.instances[0].started is True
    assert len(_FakeLive.instances[0].updates) >= 5
    refresh_flags = [refresh for _renderable, refresh in _FakeLive.instances[0].updates]
    assert False in refresh_flags
    assert "· Step 1" in rendered
    assert "resume_parse" in rendered
    assert rendered.count("I tightened your summary around backend ownership and measurable impact.") == 1
    assert "╭" not in rendered
