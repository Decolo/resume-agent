"""Interactive CLI live stream display helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.text import Text

_PREVIEW_KEY_PRIORITY = ("file_path", "path", "filename", "url", "query", "command")
_MAX_INLINE_VALUE_LEN = 120
_MAX_INLINE_ARG_PAIRS = 2
_MAX_RESULT_SUMMARY_LEN = 160
_MAX_LIVE_ASSISTANT_CHARS = 400
_MAX_LIVE_ASSISTANT_LINES = 12
_INLINE_WHITESPACE_RE = re.compile(r"\s+")
_APPROVAL_CHOICE_RE = re.compile(r"\b([123])\b")
_REDACTED_APPROVAL_ARG_KEYS = {"content", "text", "body", "data", "patch", "code"}
_DEFAULT_REFRESH_PER_SECOND = 10


def format_tool_call_approval_inline(name: str, args: Dict[str, Any]) -> str:
    """Single-line approval preview with large payload redaction."""
    safe_args: Dict[str, Any] = {}
    for key, value in (args or {}).items():
        if key.lower() in _REDACTED_APPROVAL_ARG_KEYS and isinstance(value, str):
            compact = _INLINE_WHITESPACE_RE.sub(" ", value).strip()
            safe_args[key] = f"<{len(compact)} chars>"
        else:
            safe_args[key] = value
    return format_tool_call_inline(name, safe_args)


def parse_approval_choice(raw_choice: str) -> str:
    """Parse approval input from variants like '1', '[1] Approve', 'approve'."""
    text = (raw_choice or "").strip().lower()
    if not text:
        return "reject"

    if "reject" in text or text.startswith("deny"):
        return "reject"
    if "approve all" in text or "approve tools" in text:
        return "approve_all"
    if text.startswith("approve"):
        return "approve"

    match = _APPROVAL_CHOICE_RE.search(text)
    if not match:
        return "reject"
    return {"1": "approve", "2": "approve_all", "3": "reject"}[match.group(0)]


def truncate_value(val: Any, max_len: int = _MAX_INLINE_VALUE_LEN) -> str:
    """Truncate a single arg value for display."""
    s = _INLINE_WHITESPACE_RE.sub(" ", str(val)).strip()
    if len(s) <= max_len:
        return s
    return s[:max_len] + " …"


def normalize_tool_output(output: str) -> str:
    """Normalize tool output for stable terminal rendering."""
    if not output:
        return ""
    normalized = output.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in normalized.splitlines())
    return normalized.strip("\n")


def format_tool_call_inline(name: str, args: Dict[str, Any]) -> str:
    """Single-line tool call display."""
    if not args:
        return f"🔧 {name}"

    ordered_keys = [k for k in _PREVIEW_KEY_PRIORITY if k in args]
    ordered_keys.extend(k for k in args if k not in ordered_keys)
    pairs = []
    for key in ordered_keys[:_MAX_INLINE_ARG_PAIRS]:
        pairs.append(f"{key}={truncate_value(args[key], max_len=40)}")
    if len(ordered_keys) > _MAX_INLINE_ARG_PAIRS:
        pairs.append("...")
    return f"🔧 {name}({', '.join(pairs)})"


def summarize_file_list_result(output: str) -> Optional[str]:
    """Summarize tab-separated file_list output in one line."""
    normalized = output.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line for line in normalized.splitlines() if line.strip()]
    if not lines:
        return None

    names: list[str] = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) != 3:
            return None
        kind, _size, name = parts
        if kind == "dir":
            names.append(f"{name}/")
        else:
            names.append(name)

    preview = ", ".join(names[:3])
    if len(names) > 3:
        preview += f", +{len(names) - 3} more"
    return f"{len(names)} entries: {preview}"


def summarize_tool_result(name: str, result: str) -> str:
    """Single-line summary for tool result output."""
    if not result:
        return "done"

    if name == "file_list":
        file_list_summary = summarize_file_list_result(result)
        if file_list_summary:
            return file_list_summary

    normalized = normalize_tool_output(result).replace("\t", " ")
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    if not lines:
        return "done"

    first = lines[0]
    if len(lines) > 1:
        summary = f"{first} (+{len(lines) - 1} lines)"
    else:
        summary = first
    return truncate_value(summary, max_len=_MAX_RESULT_SUMMARY_LEN)


def clip_live_assistant_text(text: str) -> str:
    """Keep live assistant rendering bounded to the most recent content."""
    clipped = text.strip("\n")
    if not clipped:
        return ""

    truncated = False
    if len(clipped) > _MAX_LIVE_ASSISTANT_CHARS:
        clipped = clipped[-_MAX_LIVE_ASSISTANT_CHARS:]
        truncated = True

    lines = clipped.splitlines()
    if len(lines) > _MAX_LIVE_ASSISTANT_LINES:
        clipped = "\n".join(lines[-_MAX_LIVE_ASSISTANT_LINES:])
        truncated = True

    if truncated:
        clipped = f"…{clipped}"
    return clipped


@dataclass(slots=True)
class _ToolCallState:
    name: str
    arguments: Dict[str, Any]
    result_summary: Optional[str] = None
    success: Optional[bool] = None

    @property
    def finished(self) -> bool:
        return self.result_summary is not None and self.success is not None


class InteractiveTurnRenderer:
    """Maintain an in-flight live view and render a stable transcript at turn end."""

    def __init__(self, console: Console, refresh_per_second: int = _DEFAULT_REFRESH_PER_SECOND) -> None:
        self.console = console
        self.refresh_per_second = refresh_per_second
        self._assistant_text = ""
        self._last_step: Optional[int] = None
        self._tool_calls: list[_ToolCallState] = []
        self._live: Optional[Live] = None
        self._live_started = False
        self._closed = False

    def start(self) -> None:
        if self._live is not None:
            return
        self._live = Live(
            self._compose_live(),
            console=self.console,
            refresh_per_second=self.refresh_per_second,
            transient=True,
            vertical_overflow="visible",
        )
        self._live.start()
        self._live_started = True

    def pause(self) -> None:
        if self._live is None or not self._live_started:
            return
        self._live.stop()
        self._live_started = False

    def resume(self) -> None:
        if self._live is None or self._live_started:
            return
        self._live.start()
        self._live_started = True
        self._refresh()

    def close(self) -> None:
        if self._closed:
            return
        self.pause()
        self._closed = True

    def on_step_begin(self, step_number: int) -> None:
        self._last_step = step_number
        self._refresh(immediate=True)

    def on_text_delta(self, text: str) -> None:
        if not text:
            return
        self._assistant_text += text
        self._refresh(immediate=False)

    def on_tool_call(self, name: str, arguments: Dict[str, Any]) -> None:
        self._tool_calls.append(_ToolCallState(name=name, arguments=arguments))
        self._refresh(immediate=True)

    def on_tool_result(self, name: str, result: str, success: bool) -> None:
        for tool_call in reversed(self._tool_calls):
            if tool_call.name == name and not tool_call.finished:
                tool_call.result_summary = summarize_tool_result(name, result)
                tool_call.success = success
                break
        else:
            self._tool_calls.append(
                _ToolCallState(
                    name=name,
                    arguments={},
                    result_summary=summarize_tool_result(name, result),
                    success=success,
                )
            )
        self._refresh(immediate=True)

    def finish(self, final_text: str) -> None:
        assistant_text = self._assistant_text or final_text
        self.close()
        self._render_transcript(assistant_text)

    def _refresh(self, *, immediate: bool) -> None:
        if self._live is None:
            return
        self._live.update(self._compose_live(), refresh=immediate)

    def _compose_live(self) -> RenderableType:
        blocks: list[RenderableType] = []
        blocks.append(Spinner("dots", text=self._status_text(), style="dim"))

        for tool_call in self._tool_calls:
            if tool_call.finished:
                icon = "✓" if tool_call.success else "✗"
                style = "green" if tool_call.success else "red"
                blocks.append(Text(f"  {icon} {tool_call.name}: {tool_call.result_summary}", style=style))
            else:
                blocks.append(Text(f"  … {format_tool_call_inline(tool_call.name, tool_call.arguments)}", style="cyan"))

        assistant_text = clip_live_assistant_text(self._assistant_text)
        if assistant_text:
            blocks.append(Text("🤖 Assistant", style="bold green"))
            blocks.append(Text(assistant_text))

        return Group(*blocks)

    def _status_text(self) -> str:
        step_suffix = f" · Step {self._last_step}" if self._last_step is not None else ""
        pending_tool = next((tool_call for tool_call in reversed(self._tool_calls) if not tool_call.finished), None)
        if pending_tool is not None:
            return f"Running {pending_tool.name}{step_suffix}"
        if self._assistant_text.strip():
            return f"Writing response{step_suffix}"
        if self._last_step is not None:
            return f"Thinking{step_suffix}"
        return "Working"

    def _render_transcript(self, assistant_text: str) -> None:
        if self._last_step is not None:
            self.console.print(f"  · Step {self._last_step}", style="dim")

        for tool_call in self._tool_calls:
            self.console.print(
                f"  {format_tool_call_inline(tool_call.name, tool_call.arguments)}", style="cyan", markup=False
            )
            if tool_call.finished:
                icon = "✓" if tool_call.success else "✗"
                style = "green" if tool_call.success else "red"
                self.console.print(f"  {icon} {tool_call.name}: {tool_call.result_summary}", style=style, markup=False)

        if assistant_text:
            self.console.print("🤖 Assistant", style="bold green")
            self.console.print(Markdown(assistant_text.strip("\n")))
