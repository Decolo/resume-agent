"""CLI - Command line interface for Resume Agent."""

import asyncio
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from resume_agent.core.agent import AgentConfig, ResumeAgent
from resume_agent.core.agent_factory import create_agent
from resume_agent.core.agents.orchestrator_agent import OrchestratorAgent
from resume_agent.core.llm import LLMConfig, load_config, load_raw_config
from resume_agent.core.session import SessionManager
from resume_agent.core.wire import QueueShutDown, Wire
from resume_agent.core.wire.types import (
    ApprovalRequest,
    TextDelta,
    ToolCallEvent,
    ToolResultEvent,
    TurnEnd,
)

from .config_validator import Severity, has_errors, validate_config
from .tool_factory import create_tools

console = Console()

# Keys whose values are typically short and useful for preview
_PREVIEW_KEY_PRIORITY = ("file_path", "path", "filename", "url", "query", "command")
_MAX_INLINE_VALUE_LEN = 120
_MAX_INLINE_ARG_PAIRS = 2
_MAX_RESULT_SUMMARY_LEN = 160
_INLINE_WHITESPACE_RE = re.compile(r"\s+")
_APPROVAL_CHOICE_RE = re.compile(r"\b([123])\b")
_REDACTED_APPROVAL_ARG_KEYS = {"content", "text", "body", "data", "patch", "code"}


def _format_tool_call_approval_inline(name: str, args: Dict[str, Any]) -> str:
    """Single-line approval preview with large payload redaction."""
    safe_args: Dict[str, Any] = {}
    for key, value in (args or {}).items():
        if key.lower() in _REDACTED_APPROVAL_ARG_KEYS and isinstance(value, str):
            compact = _INLINE_WHITESPACE_RE.sub(" ", value).strip()
            safe_args[key] = f"<{len(compact)} chars>"
        else:
            safe_args[key] = value
    return _format_tool_call_inline(name, safe_args)


def _parse_approval_choice(raw_choice: str) -> str:
    """Parse approval input from variants like '1', '[1] Approve', 'approve'."""
    text = (raw_choice or "").strip().lower()
    if not text:
        return "reject"

    # Match explicit intent first to avoid accidental privilege escalation.
    if "reject" in text or text.startswith("deny"):
        return "reject"
    if "approve all" in text:
        return "approve_all"
    if text.startswith("approve"):
        return "approve"

    match = _APPROVAL_CHOICE_RE.search(text)
    if not match:
        return "reject"
    return {"1": "approve", "2": "approve_all", "3": "reject"}[match.group(0)]


def _truncate_value(val: Any, max_len: int = _MAX_INLINE_VALUE_LEN) -> str:
    """Truncate a single arg value for display."""
    s = _INLINE_WHITESPACE_RE.sub(" ", str(val)).strip()
    if len(s) <= max_len:
        return s
    return s[:max_len] + " …"


def _normalize_tool_output(output: str) -> str:
    """Normalize tool output for stable terminal rendering."""
    if not output:
        return ""
    normalized = output.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in normalized.splitlines())
    return normalized.strip("\n")


def _format_tool_call_inline(name: str, args: Dict[str, Any]) -> str:
    """Single-line tool call display."""
    if not args:
        return f"🔧 {name}"

    ordered_keys = [k for k in _PREVIEW_KEY_PRIORITY if k in args]
    ordered_keys.extend(k for k in args if k not in ordered_keys)
    pairs = []
    for key in ordered_keys[:_MAX_INLINE_ARG_PAIRS]:
        pairs.append(f"{key}={_truncate_value(args[key], max_len=40)}")
    if len(ordered_keys) > _MAX_INLINE_ARG_PAIRS:
        pairs.append("...")
    return f"🔧 {name}({', '.join(pairs)})"


def _summarize_file_list_result(output: str) -> Optional[str]:
    """Summarize tab-separated file_list output in one line."""
    normalized = output.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line for line in normalized.splitlines() if line.strip()]
    if not lines:
        return None
    if lines == ["(empty directory)"]:
        return "empty directory"

    parsed_rows: list[tuple[str, str, str]] = []
    for line in lines:
        parts = line.split("\t", 2)
        if len(parts) != 3:
            return None
        file_type, size, path = parts
        parsed_rows.append((file_type.strip(), size.strip(), path.strip()))

    preview_items: list[str] = []
    for file_type, _size, path in parsed_rows[:3]:
        preview_items.append(f"{path}/" if file_type == "dir" else path)
    summary = f"{len(parsed_rows)} entries"
    if preview_items:
        summary += ": " + ", ".join(preview_items)
    if len(parsed_rows) > 3:
        summary += ", ..."
    return summary


def _summarize_tool_result(name: str, result: str) -> str:
    """Single-line tool result summary."""
    if not result:
        return "ok"

    if name == "file_list":
        file_list_summary = _summarize_file_list_result(result)
        if file_list_summary is not None:
            return file_list_summary

    normalized = _normalize_tool_output(result).replace("\t", " ")
    if not normalized:
        return "ok"

    lines = [line for line in normalized.splitlines() if line.strip()]
    if not lines:
        return "ok"

    summary = _INLINE_WHITESPACE_RE.sub(" ", lines[0]).strip()
    if len(lines) > 1:
        summary += f" (+{len(lines) - 1} lines)"
    return _truncate_value(summary, max_len=_MAX_RESULT_SUMMARY_LEN)


def _fuzzy_token_match(token: str, text: str) -> bool:
    """Case-insensitive token match with subsequence fallback."""
    token_norm = "".join(token.lower().split())
    text_norm = "".join(text.lower().split())
    if not token_norm:
        return True
    if token_norm in text_norm:
        return True
    index = 0
    for ch in text_norm:
        if index < len(token_norm) and ch == token_norm[index]:
            index += 1
    return index == len(token_norm)


def _session_search_text(session: Dict[str, Any]) -> str:
    """Build searchable text for session fuzzy filtering."""
    session_id = str(session.get("id", ""))
    parts_id = session_id.split("_")
    fields = [session_id, str(session.get("mode", ""))]
    if len(parts_id) >= 5:
        fields.append("_".join(parts_id[3:-1]))
    if len(parts_id) >= 3:
        fields.append(parts_id[1])
        fields.append(parts_id[2])
        fields.append(f"{parts_id[1]}_{parts_id[2]}")
    return " ".join(field for field in fields if field)


def _session_matches_query(session: Dict[str, Any], query: str) -> bool:
    query_tokens = [token for token in query.split() if token]
    if not query_tokens:
        return True
    searchable = _session_search_text(session)
    return all(_fuzzy_token_match(token, searchable) for token in query_tokens)


class ResumeCLICompleter(Completer):
    """Command auto-completer for interactive CLI."""

    COMMANDS = [
        "/help",
        "/reset",
        "/save",
        "/load",
        "/sessions",
        "/delete-session",
        "/files",
        "/config",
        "/export",
        "/auto-approve",
        "/stream",
        "/agents",
        "/trace",
        "/delegation-tree",
        "/quit",
        "/exit",
    ]

    def __init__(self, session_manager: Optional[SessionManager] = None):
        self.session_manager = session_manager

    def _session_refs(self) -> list[str]:
        if not self.session_manager:
            return []
        try:
            sessions = self.session_manager.list_sessions()
        except Exception:
            return []

        refs = ["latest"]
        for idx, session in enumerate(sessions, start=1):
            refs.append(str(idx))
            session_id = session.get("id")
            if isinstance(session_id, str) and session_id:
                refs.append(session_id)
        return list(dict.fromkeys(refs))

    @staticmethod
    def _yield_options(options: Iterable[str], current: str):
        start_position = -len(current)
        current_lower = current.lower()
        for option in options:
            if not current or option.lower().startswith(current_lower):
                yield Completion(option, start_position=start_position)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return

        parts = text.split()
        if text.endswith(" "):
            parts.append("")
        if not parts:
            return

        if len(parts) == 1:
            current = parts[0]
            yield from self._yield_options(self.COMMANDS, current)
            return

        command = parts[0].lower()
        current = parts[-1]

        if command in {"/stream", "/auto-approve"} and len(parts) == 2:
            yield from self._yield_options(["on", "off", "status"], current)
            return
        if command in {"/load", "/delete-session"} and len(parts) == 2:
            yield from self._yield_options(self._session_refs(), current)
            return
        if command == "/export":
            if len(parts) == 2:
                yield from self._yield_options(["file", "clipboard", "clip"], current)
            elif len(parts) == 3:
                yield from self._yield_options(["markdown", "json", "text"], current)
            elif len(parts) >= 4:
                yield from self._yield_options(["verbose", "-v", "--verbose"], current)


def print_banner():
    """Print welcome banner."""
    banner = """
╔═══════════════════════════════════════════════════════════╗
║                    📄 Resume Agent                        ║
║         AI-powered Resume Modification Assistant          ║
╠═══════════════════════════════════════════════════════════╣
║  Quick Commands:                                          ║
║    /help     - Show all commands                          ║
║    /stream   - Toggle streaming output                    ║
║    /save     - Save current session                       ║
║    /load     - Load a previous session (shows picker)     ║
║    /sessions - List all saved sessions                    ║
║    /quit     - Exit the agent                             ║
║                                                           ║
║  💡 Auto-save is enabled - your work is protected!        ║
╚═══════════════════════════════════════════════════════════╝
"""
    console.print(banner, style="cyan")


def print_help():
    """Print help message."""
    help_text = """
## Available Commands

| Command | Description |
|---------|-------------|
| `/help` | Show this help message |
| `/reset` | Reset conversation history |
| `/save [name]` | Save current session (optional custom name) |
| `/load [number]` | Load a saved session (shows picker if no number) |
| `/sessions [query]` | List sessions (optionally filtered with fuzzy query) |
| `/delete-session <number>` | Delete a saved session by number |
| `/quit` or `/exit` | Exit the agent |
| `/files` | List files in workspace |
| `/config` | Show current configuration |
| `/export [target] [format]` | Export conversation history |
| `/auto-approve [on|off|status]` | Control auto-approval for write tools |
| `/stream [on|off|status]` | Control streaming output in interactive mode |
| `/agents` | Show agent statistics (multi-agent mode) |
| `/trace` | Show delegation trace (multi-agent mode) |
| `/delegation-tree` | Show delegation stats (multi-agent mode) |

### Session Management

Save and restore conversation sessions:

```bash
/save                    # Save with auto-generated timestamp
/save my_resume_v1       # Save with custom name
/sessions                # List all saved sessions (numbered)
/sessions backend        # Fuzzy filter by name/id/mode
/load                    # Show session picker
/load 1                  # Load session #1 (most recent)
/load 2                  # Load session #2
/delete-session 1        # Delete session #1
```

**Session features:**
- 🎯 **Quick load by number**: `/load 1` loads the most recent session
- 📋 **Interactive picker**: `/load` without arguments shows all sessions
- 🔎 **Fuzzy search**: `/sessions data eng` filters sessions by token match
- 🏷️ **Custom names**: `/save my_project_v1` for easy identification
- 🔄 **Auto-save always enabled**: Sessions automatically saved after each tool execution
- 📊 **Full state preservation**: History, observability, multi-agent state

### Export Command

Export conversation history to file or clipboard:

```bash
/export file markdown         # Save as markdown (default)
/export file json             # Save as JSON
/export file text             # Save as plain text
/export clipboard markdown    # Copy markdown to clipboard
/export clip json             # Copy JSON to clipboard (shorthand)

# Verbose mode - includes observability logs
/export file markdown verbose # Save with tool calls, LLM requests, errors, stats
/export file json verbose     # Save with full observability data
/export clip text verbose     # Copy with detailed execution logs
```

**Verbose mode includes:**
- Tool execution logs (name, args, duration, cache status)
- LLM API requests (model, tokens, cost, duration)
- Error events with context
- Step-by-step execution trace
- Session statistics (total tokens, cost, cache hit rate)

Files are saved to `exports/conversation_YYYYMMDD_HHMMSS[_verbose].{ext}`

## Example Prompts

- "Parse my resume from resume.pdf and analyze it"
- "Improve my work experience section with stronger action verbs"
- "Tailor my resume for a Senior Software Engineer position at Google"
- "Convert my resume to a modern HTML format"
- "Add quantifiable metrics to my achievements"
- "Check if my resume is ATS-friendly"
"""
    console.print(Markdown(help_text))


def _get_llm_agents(agent: Union[ResumeAgent, OrchestratorAgent]):
    """Return list of LLMAgent instances for pending tool approvals."""
    from resume_agent.core.agent_factory import AutoAgent

    agents = []
    if isinstance(agent, AutoAgent):
        if hasattr(agent, "single_agent") and hasattr(agent.single_agent, "agent"):
            agents.append(agent.single_agent.agent)
        if hasattr(agent, "multi_agent") and hasattr(agent.multi_agent, "llm_agent"):
            agents.append(agent.multi_agent.llm_agent)
        if hasattr(agent, "multi_agent") and hasattr(agent.multi_agent, "registry"):
            for sub_agent in agent.multi_agent.registry.get_all_agents():
                if hasattr(sub_agent, "llm_agent") and sub_agent.llm_agent:
                    agents.append(sub_agent.llm_agent)
    elif isinstance(agent, ResumeAgent):
        if hasattr(agent, "agent"):
            agents.append(agent.agent)
    elif isinstance(agent, OrchestratorAgent):
        if hasattr(agent, "llm_agent"):
            agents.append(agent.llm_agent)
        if hasattr(agent, "registry"):
            for sub_agent in agent.registry.get_all_agents():
                if hasattr(sub_agent, "llm_agent") and sub_agent.llm_agent:
                    agents.append(sub_agent.llm_agent)

    # De-duplicate
    unique = []
    seen = set()
    for a in agents:
        if a is None:
            continue
        aid = id(a)
        if aid in seen:
            continue
        seen.add(aid)
        unique.append(a)
    return unique


def _list_pending_tool_calls(agent: Union[ResumeAgent, OrchestratorAgent]) -> list:
    pending = []
    for llm_agent in _get_llm_agents(agent):
        if hasattr(llm_agent, "has_pending_tool_calls") and llm_agent.has_pending_tool_calls():
            pending.extend(llm_agent.list_pending_tool_calls())
    return pending


def _get_auto_approve_state(agent: Union[ResumeAgent, OrchestratorAgent]) -> Optional[str]:
    states = []
    for llm_agent in _get_llm_agents(agent):
        if hasattr(llm_agent, "is_auto_approve_enabled"):
            states.append(bool(llm_agent.is_auto_approve_enabled()))
    if not states:
        return None
    if all(states):
        return "on"
    if not any(states):
        return "off"
    return "mixed"


def _set_auto_approve_state(agent: Union[ResumeAgent, OrchestratorAgent], enabled: bool) -> None:
    for llm_agent in _get_llm_agents(agent):
        if hasattr(llm_agent, "set_auto_approve_tools"):
            llm_agent.set_auto_approve_tools(enabled)


async def handle_command(
    command: str,
    agent: Union[ResumeAgent, OrchestratorAgent],
    session_manager: Optional[SessionManager] = None,
    runtime_options: Optional[Dict[str, Any]] = None,
) -> bool:
    """Handle special commands. Returns True if should continue, False to exit."""
    command_text = command.strip()
    cmd = command_text.lower()

    if cmd in ["/quit", "/exit", "/q"]:
        console.print("\n👋 Goodbye!", style="yellow")
        return False

    elif cmd == "/help":
        print_help()

    elif cmd == "/reset":
        agent.reset()
        console.print("🔄 Conversation reset.", style="green")

    elif cmd.startswith("/save"):
        if not session_manager:
            console.print("⚠️ Session management not available.", style="yellow")
            return True

        # Parse: /save [session_name]
        session_name_input = command_text[len("/save") :].strip()
        session_name = session_name_input if session_name_input else None

        try:
            session_id = session_manager.save_session(agent, session_name=session_name)

            # Show friendly confirmation
            if session_name:
                console.print(f"✓ Session saved as: {session_name}", style="green")
            else:
                # Extract timestamp from session ID for display
                parts_id = session_id.split("_")
                if len(parts_id) >= 3:
                    timestamp = f"{parts_id[1]}_{parts_id[2]}"
                    console.print(f"✓ Session saved: {timestamp}", style="green")
                else:
                    console.print("✓ Session saved", style="green")

            console.print("   Use /load to restore this session later", style="dim")
        except Exception as e:
            console.print(f"❌ Failed to save session: {e}", style="red")

    elif cmd.startswith("/load"):
        if not session_manager:
            console.print("⚠️ Session management not available.", style="yellow")
            return True

        # Parse: /load [session_id or number]
        parts = command_text.split()

        # Get available sessions
        sessions = session_manager.list_sessions()
        if not sessions:
            console.print("No saved sessions found.", style="yellow")
            return True

        # If no argument provided, show interactive picker
        if len(parts) < 2:
            console.print("\n📁 Available Sessions:", style="bold cyan")
            console.print("─" * 80)

            table = Table(show_header=True, header_style="bold cyan", box=None)
            table.add_column("#", style="yellow", width=3)
            table.add_column("Name", style="cyan", no_wrap=False)
            table.add_column("Updated", style="dim", width=16)
            table.add_column("Mode", style="green", width=12)
            table.add_column("Msgs", justify="right", width=5)
            table.add_column("Tokens", justify="right", width=8)

            for i, session in enumerate(sessions, 1):
                # Extract custom name from session ID
                session_id = session["id"]
                # Format: session_YYYYMMDD_HHMMSS_[name]_[uuid]
                parts_id = session_id.split("_")
                if len(parts_id) >= 5:
                    # Has custom name
                    custom_name = "_".join(parts_id[3:-1])
                    display_name = f"{custom_name} ({parts_id[1]}_{parts_id[2]})"
                else:
                    # No custom name, show timestamp
                    display_name = f"{parts_id[1]}_{parts_id[2]}"

                from datetime import datetime

                updated = datetime.fromisoformat(session["updated_at"]).strftime("%m-%d %H:%M")

                table.add_row(
                    str(i),
                    display_name,
                    updated,
                    session["mode"],
                    str(session["message_count"]),
                    f"{session['total_tokens']:,}",
                )

            console.print(table)
            console.print("\n💡 Usage: /load <number> or /load <full_session_id>", style="dim")
            console.print("   Example: /load 1  (loads the most recent session)", style="dim")
            return True
        if len(parts) > 2:
            console.print("Usage: /load <number> or /load <full_session_id>", style="yellow")
            return True

        # Load by number or full session ID
        session_arg = parts[1]

        # Check if it's a number (index)
        if session_arg.isdigit():
            index = int(session_arg) - 1
            if 0 <= index < len(sessions):
                session_id = sessions[index]["id"]
            else:
                console.print(f"❌ Invalid session number. Use 1-{len(sessions)}", style="red")
                return True
        else:
            # Assume it's a full session ID
            session_id = session_arg

        # Load the session
        try:
            session_data = session_manager.load_session(session_id)
            session_manager.restore_agent_state(agent, session_data)

            # Show success with session info
            session_info = next((s for s in sessions if s["id"] == session_id), None)
            if session_info:
                console.print(
                    f"✓ Session loaded: {session_info['message_count']} messages, {session_info['total_tokens']:,} tokens",
                    style="green",
                )
            else:
                console.print(f"✓ Session loaded: {session_id}", style="green")
        except FileNotFoundError:
            console.print(f"❌ Session not found: {session_id}", style="red")
            console.print("Tip: Use /load without arguments to see available sessions", style="dim")
        except Exception as e:
            console.print(f"❌ Failed to load session: {e}", style="red")

    elif cmd.startswith("/sessions"):
        if not session_manager:
            console.print("⚠️ Session management not available.", style="yellow")
            return True

        session_query = command_text[len("/sessions") :].strip()
        sessions = session_manager.list_sessions()
        if session_query:
            sessions = [session for session in sessions if _session_matches_query(session, session_query)]

        if not sessions and session_query:
            console.print(f"No sessions matched query: {session_query}", style="dim")
        elif not sessions:
            console.print("No saved sessions found.", style="dim")
        else:
            title = "📁 Saved Sessions" if not session_query else f"📁 Saved Sessions (filter: {session_query})"
            table = Table(title=title, show_header=True, header_style="bold cyan")
            table.add_column("#", style="yellow", width=3)
            table.add_column("Name", style="cyan", no_wrap=False)
            table.add_column("Created", style="dim", width=16)
            table.add_column("Updated", style="dim", width=16)
            table.add_column("Mode", style="green", width=12)
            table.add_column("Messages", justify="right", width=8)
            table.add_column("Tokens", justify="right", width=10)

            for i, session in enumerate(sessions, 1):
                # Extract custom name from session ID
                session_id = session["id"]
                # Format: session_YYYYMMDD_HHMMSS_[name]_[uuid]
                parts = session_id.split("_")
                if len(parts) >= 5:
                    # Has custom name
                    custom_name = "_".join(parts[3:-1])
                    display_name = f"{custom_name}"
                    timestamp = f"{parts[1]}_{parts[2]}"
                else:
                    # No custom name, show timestamp
                    display_name = f"session_{parts[1]}_{parts[2]}"
                    timestamp = ""

                # Format timestamps
                from datetime import datetime

                created = datetime.fromisoformat(session["created_at"]).strftime("%m-%d %H:%M")
                updated = datetime.fromisoformat(session["updated_at"]).strftime("%m-%d %H:%M")

                table.add_row(
                    str(i),
                    display_name,
                    created,
                    updated,
                    session["mode"],
                    str(session["message_count"]),
                    f"{session['total_tokens']:,}",
                )

            console.print(table)
            if session_query:
                console.print("\n💡 Clear filter with /sessions", style="dim")
            console.print("💡 Quick load: /load <number>  (e.g., /load 1 for most recent)", style="dim")
            console.print("   Full ID load: /load <full_session_id>", style="dim")

    elif cmd.startswith("/delete-session"):
        if not session_manager:
            console.print("⚠️ Session management not available.", style="yellow")
            return True

        # Parse: /delete-session <session_id or number>
        parts = command_text.split()
        if len(parts) < 2:
            console.print("Usage: /delete-session <number> or /delete-session <full_session_id>", style="yellow")
            console.print("Tip: Use /sessions to see session numbers", style="dim")
        elif len(parts) > 2:
            console.print("Usage: /delete-session <number> or /delete-session <full_session_id>", style="yellow")
        else:
            session_arg = parts[1]

            # Get available sessions
            sessions = session_manager.list_sessions()

            # Check if it's a number (index)
            if session_arg.isdigit():
                index = int(session_arg) - 1
                if 0 <= index < len(sessions):
                    session_id = sessions[index]["id"]
                else:
                    console.print(f"❌ Invalid session number. Use 1-{len(sessions)}", style="red")
                    return True
            else:
                # Assume it's a full session ID
                session_id = session_arg

            # Delete the session
            if session_manager.delete_session(session_id):
                console.print("✓ Session deleted", style="green")
            else:
                console.print("❌ Session not found", style="red")

    elif cmd == "/files":
        if isinstance(agent, ResumeAgent):
            result = await agent.tools["file_list"].execute()
            console.print(Panel(result.output, title="📁 Workspace Files"))
        else:
            # Multi-agent mode - use orchestrator's LLM agent
            console.print("📁 Use 'list files in workspace' to see files.", style="dim")

    elif cmd == "/config":
        if isinstance(agent, ResumeAgent):
            config_info = f"""
**Model**: {agent.llm_config.model}
**Max Tokens**: {agent.llm_config.max_tokens}
**Temperature**: {agent.llm_config.temperature}
**Workspace**: {agent.agent_config.workspace_dir}
**Mode**: Single-Agent
"""
        else:
            config_info = f"""
**Model**: {agent.config.model}
**Max Tokens**: {agent.config.max_tokens}
**Temperature**: {agent.config.temperature}
**Mode**: Multi-Agent (Orchestrated)
**Agents**: {len(agent.registry) if agent.registry else 0}
"""
        console.print(Markdown(config_info))

    elif cmd == "/agents":
        if isinstance(agent, OrchestratorAgent) and agent.registry:
            stats = agent.get_agent_stats()

            table = Table(title="Agent Statistics")
            table.add_column("Agent", style="cyan")
            table.add_column("Type", style="green")
            table.add_column("Tasks", justify="right")
            table.add_column("Success Rate", justify="right")
            table.add_column("Avg Time", justify="right")

            for agent_id, agent_stats in stats.items():
                table.add_row(
                    agent_id,
                    agent_stats.get("agent_type", ""),
                    str(agent_stats.get("tasks_completed", 0)),
                    agent_stats.get("success_rate", "N/A"),
                    agent_stats.get("average_execution_time_ms", "N/A"),
                )

            console.print(table)
        else:
            console.print("⚠️ Agent statistics only available in multi-agent mode.", style="yellow")

    elif cmd == "/delegation-tree":
        if isinstance(agent, OrchestratorAgent) and agent.delegation_manager:
            delegation_stats = agent.delegation_manager.get_stats()
            console.print(
                Panel(
                    f"Total delegations: {delegation_stats['total_delegations']}\n"
                    f"Successful: {delegation_stats['successful']}\n"
                    f"Failed: {delegation_stats['failed']}\n"
                    f"Success rate: {delegation_stats['success_rate']}\n"
                    f"Average duration: {delegation_stats['average_duration_ms']}",
                    title="📊 Delegation Statistics",
                )
            )
        else:
            console.print("⚠️ Delegation tree only available in multi-agent mode.", style="yellow")

    elif cmd == "/trace":
        if isinstance(agent, OrchestratorAgent) and agent.delegation_manager:
            history = agent.delegation_manager._delegation_history
            if not history:
                console.print("No delegations recorded yet.", style="dim")
            else:
                table = Table(title="🔄 Delegation Trace")
                table.add_column("#", style="dim", justify="right")
                table.add_column("Task ID", style="cyan")
                table.add_column("From", style="yellow")
                table.add_column("To", style="green")
                table.add_column("Duration", justify="right")
                table.add_column("Status", justify="center")

                for i, record in enumerate(history, 1):
                    status = "✓" if record.success else "✗" if record.success is False else "⏳"
                    status_style = "green" if record.success else "red" if record.success is False else "yellow"
                    duration = f"{record.duration_ms:.0f}ms" if record.duration_ms else "-"
                    table.add_row(
                        str(i),
                        record.task_id[:16] + "...",
                        record.from_agent,
                        record.to_agent,
                        duration,
                        f"[{status_style}]{status}[/{status_style}]",
                    )

                console.print(table)

                # Show delegation flow diagram
                console.print("\n📊 Delegation Flow:", style="bold")
                for record in history:
                    arrow = "[green]→[/green]" if record.success else "[red]→[/red]"
                    console.print(f"  {record.from_agent} {arrow} {record.to_agent}")
        else:
            console.print("⚠️ Trace only available in multi-agent mode.", style="yellow")

    elif cmd.startswith("/auto-approve"):
        parts = cmd.split(maxsplit=1)
        action = parts[1].strip().lower() if len(parts) > 1 else "status"
        if action in {"status", "state"}:
            state = _get_auto_approve_state(agent)
            if state is None:
                console.print("Auto-approve not supported in this mode.", style="dim")
            else:
                console.print(f"Auto-approve is {state}.", style="green" if state == "on" else "yellow")
        elif action in {"on", "true", "1", "yes"}:
            _set_auto_approve_state(agent, True)
            console.print("✓ Auto-approve enabled for write tools.", style="green")
        elif action in {"off", "false", "0", "no"}:
            _set_auto_approve_state(agent, False)
            console.print("✓ Auto-approve disabled for write tools.", style="yellow")
        else:
            console.print("Usage: /auto-approve [on|off|status]", style="yellow")

    elif cmd == "/stream" or cmd.startswith("/stream "):
        if runtime_options is None:
            console.print("Streaming controls unavailable in this mode.", style="yellow")
            return True
        parts = cmd.split(maxsplit=1)
        action = parts[1].strip().lower() if len(parts) > 1 else "status"
        if action in {"status", "state"}:
            state = "on" if bool(runtime_options.get("stream_enabled", False)) else "off"
            console.print(f"Streaming is {state}.", style="green" if state == "on" else "yellow")
        elif action in {"on", "true", "1", "yes"}:
            runtime_options["stream_enabled"] = True
            console.print("✓ Streaming enabled.", style="green")
        elif action in {"off", "false", "0", "no"}:
            runtime_options["stream_enabled"] = False
            console.print("✓ Streaming disabled.", style="yellow")
        else:
            console.print("Usage: /stream [on|off|status]", style="yellow")

    elif cmd.startswith("/export"):
        # Parse export command: /export [file|clipboard] [format] [verbose]
        parts = command_text.split()
        target = parts[1].lower() if len(parts) > 1 else "file"
        format_type = parts[2].lower() if len(parts) > 2 else "markdown"
        extra_flags = [part.lower() for part in parts[3:]]
        valid_flags = {"verbose", "--verbose", "-v"}
        if any(flag not in valid_flags for flag in extra_flags):
            console.print("Usage: /export [file|clipboard] [markdown|json|text] [verbose|-v]", style="yellow")
            return True
        verbose = any(flag in valid_flags for flag in extra_flags)

        if target not in ["file", "clipboard", "clip"]:
            console.print("Usage: /export [file|clipboard] [markdown|json|text] [verbose|-v]", style="yellow")
            return True

        if format_type not in {"markdown", "json", "text"}:
            console.print("Usage: /export [file|clipboard] [markdown|json|text] [verbose|-v]", style="yellow")
            return True

        # Get conversation history (handle AutoAgent, OrchestratorAgent, ResumeAgent)
        from resume_agent.core.agent_factory import AutoAgent

        if isinstance(agent, AutoAgent):
            llm_agent = agent.agent
        elif isinstance(agent, OrchestratorAgent):
            llm_agent = agent.llm_agent
        else:
            llm_agent = agent.agent  # ResumeAgent uses self.agent for LLMAgent

        if not llm_agent or not llm_agent.history_manager:
            console.print("No conversation history available.", style="yellow")
            return True

        history = llm_agent.history_manager.get_history()
        if not history:
            console.print("No conversation history to export.", style="yellow")
            return True

        # Get observability events if verbose mode
        observer_events = []
        if verbose:
            observer = llm_agent.observer if hasattr(llm_agent, "observer") else None
            if observer:
                observer_events = observer.events
            else:
                console.print("⚠️ No observability data available.", style="yellow")

        # Format the history
        if format_type == "json":
            import json
            from datetime import datetime

            export_data = {
                "exported_at": datetime.now().isoformat(),
                "agent_mode": "multi-agent" if isinstance(agent, OrchestratorAgent) else "single-agent",
                "messages": [],
            }

            for msg in history:
                msg_data = {"role": msg.role, "parts": []}
                if msg.parts:
                    for part in msg.parts:
                        if part.text:
                            msg_data["parts"].append({"type": "text", "content": part.text})
                        elif part.function_call:
                            msg_data["parts"].append(
                                {
                                    "type": "function_call",
                                    "name": part.function_call.name,
                                    "args": dict(part.function_call.arguments) if part.function_call.arguments else {},
                                    "id": part.function_call.id,
                                }
                            )
                        elif part.function_response:
                            msg_data["parts"].append(
                                {
                                    "type": "function_response",
                                    "name": part.function_response.name,
                                    "response": part.function_response.response,
                                    "call_id": part.function_response.call_id,
                                }
                            )
                export_data["messages"].append(msg_data)

            # Add observability events if verbose
            if verbose and observer_events:
                export_data["observability"] = {
                    "events": [
                        {
                            "timestamp": event.timestamp.isoformat(),
                            "event_type": event.event_type,
                            "data": event.data,
                            "duration_ms": event.duration_ms,
                            "tokens_used": event.tokens_used,
                            "cost_usd": event.cost_usd,
                        }
                        for event in observer_events
                    ],
                    "session_stats": llm_agent.observer.get_session_stats() if hasattr(llm_agent, "observer") else {},
                }

            content = json.dumps(export_data, indent=2)

        elif format_type == "text":
            lines = []
            for msg in history:
                role_label = "User" if msg.role == "user" else "Assistant" if msg.role == "assistant" else "Tool"
                lines.append(f"\n{'=' * 60}")
                lines.append(f"{role_label}:")
                lines.append("=" * 60)

                if msg.parts:
                    for part in msg.parts:
                        if part.text:
                            lines.append(part.text)
                        elif part.function_call:
                            lines.append(f"[Tool Call: {part.function_call.name}]")
                        elif part.function_response:
                            lines.append(f"[Tool Response: {part.function_response.name}]")

            # Add observability events if verbose
            if verbose and observer_events:
                lines.append(f"\n\n{'=' * 60}")
                lines.append("OBSERVABILITY LOGS")
                lines.append("=" * 60)

                for event in observer_events:
                    lines.append(f"\n[{event.timestamp.strftime('%H:%M:%S')}] {event.event_type.upper()}")

                    if event.event_type == "tool_call":
                        tool = event.data.get("tool", "unknown")
                        success = "✓" if event.data.get("success") else "✗"
                        cached = " [CACHED]" if event.data.get("cached") else ""
                        lines.append(f"  {success} Tool: {tool}{cached} ({event.duration_ms:.2f}ms)")
                        lines.append(f"  Args: {event.data.get('args', {})}")

                    elif event.event_type == "llm_request":
                        lines.append(f"  Model: {event.data.get('model')}")
                        lines.append(f"  Step: {event.data.get('step')}")
                        lines.append(f"  Tokens: {event.tokens_used}")
                        lines.append(f"  Cost: ${event.cost_usd:.4f}")
                        lines.append(f"  Duration: {event.duration_ms:.2f}ms")

                    elif event.event_type == "error":
                        lines.append(f"  ❌ {event.data.get('error_type')}: {event.data.get('message')}")

                    elif event.event_type in ["step_start", "step_end"]:
                        lines.append(f"  Step: {event.data.get('step')}")
                        if event.duration_ms:
                            lines.append(f"  Duration: {event.duration_ms:.2f}ms")

                # Add session stats
                if hasattr(llm_agent, "observer"):
                    stats = llm_agent.observer.get_session_stats()
                    lines.append(f"\n{'=' * 60}")
                    lines.append("SESSION STATISTICS")
                    lines.append("=" * 60)
                    lines.append(f"Total Events:     {stats['event_count']}")
                    lines.append(f"Tool Calls:       {stats['tool_calls']} (cache hit: {stats['cache_hit_rate']:.1%})")
                    lines.append(f"LLM Requests:     {stats['llm_requests']}")
                    lines.append(f"Errors:           {stats['errors']}")
                    lines.append(f"Total Tokens:     {stats['total_tokens']:,}")
                    lines.append(f"Total Cost:       ${stats['total_cost_usd']:.4f}")
                    lines.append(f"Total Duration:   {stats['total_duration_ms']:.2f}ms")

            content = "\n".join(lines)

        else:  # markdown (default)
            lines = ["# Conversation History\n"]

            for msg in history:
                if msg.role == "user":
                    lines.append("## 👤 User\n")
                elif msg.role == "assistant":
                    lines.append("## 🤖 Assistant\n")
                else:
                    lines.append("## 🔧 Tool\n")

                if msg.parts:
                    for part in msg.parts:
                        if part.text:
                            lines.append(part.text + "\n")
                        elif part.function_call:
                            lines.append(f"**Tool Call:** `{part.function_call.name}`\n")
                        elif part.function_response:
                            lines.append(f"**Tool Response:** `{part.function_response.name}`\n")

                lines.append("---\n")

            # Add observability events if verbose
            if verbose and observer_events:
                lines.append("\n# Observability Logs\n")

                for event in observer_events:
                    timestamp = event.timestamp.strftime("%H:%M:%S")

                    if event.event_type == "tool_call":
                        tool = event.data.get("tool", "unknown")
                        success = "✓" if event.data.get("success") else "✗"
                        cached = " 🔄" if event.data.get("cached") else ""
                        lines.append(
                            f"- **[{timestamp}]** {success} Tool: `{tool}`{cached} ({event.duration_ms:.2f}ms)"
                        )
                        args = event.data.get("args", {})
                        if args:
                            lines.append(f"  - Args: `{args}`")

                    elif event.event_type == "llm_request":
                        model = event.data.get("model")
                        step = event.data.get("step")
                        lines.append(f"- **[{timestamp}]** 🤖 LLM Request: `{model}` (Step {step})")
                        lines.append(
                            f"  - Tokens: {event.tokens_used}, Cost: ${event.cost_usd:.4f}, Duration: {event.duration_ms:.2f}ms"
                        )

                    elif event.event_type == "llm_response":
                        step = event.data.get("step")
                        text = event.data.get("text", "")[:100]
                        tool_calls = event.data.get("tool_calls", [])
                        lines.append(f"- **[{timestamp}]** 🧠 LLM Response (Step {step})")
                        if tool_calls:
                            lines.append(f"  - Tool calls: {len(tool_calls)}")
                        if text:
                            lines.append(f"  - Text: {text}...")

                    elif event.event_type == "error":
                        error_type = event.data.get("error_type")
                        message = event.data.get("message")
                        lines.append(f"- **[{timestamp}]** ❌ Error: `{error_type}` - {message}")

                    elif event.event_type == "step_start":
                        step = event.data.get("step")
                        lines.append(f"- **[{timestamp}]** 🔄 Step {step} started")

                    elif event.event_type == "step_end":
                        step = event.data.get("step")
                        lines.append(f"- **[{timestamp}]** ✓ Step {step} completed ({event.duration_ms:.2f}ms)")

                # Add session stats
                if hasattr(llm_agent, "observer"):
                    stats = llm_agent.observer.get_session_stats()
                    lines.append("\n## Session Statistics\n")
                    lines.append(f"- **Total Events:** {stats['event_count']}")
                    lines.append(f"- **Tool Calls:** {stats['tool_calls']} (cache hit: {stats['cache_hit_rate']:.1%})")
                    lines.append(f"- **LLM Requests:** {stats['llm_requests']}")
                    lines.append(f"- **Errors:** {stats['errors']}")
                    lines.append(f"- **Total Tokens:** {stats['total_tokens']:,}")
                    lines.append(f"- **Total Cost:** ${stats['total_cost_usd']:.4f}")
                    lines.append(f"- **Total Duration:** {stats['total_duration_ms']:.2f}ms")

            content = "\n".join(lines)

        # Export to target
        verbose_label = " (with observability logs)" if verbose else ""
        if target in ["clipboard", "clip"]:
            try:
                import pyperclip

                pyperclip.copy(content)
                console.print(
                    f"✓ Conversation history copied to clipboard ({format_type} format{verbose_label})", style="green"
                )
            except Exception as e:
                console.print(f"❌ Failed to copy to clipboard: {e}", style="red")
        else:  # file
            from datetime import datetime
            from pathlib import Path

            # Create exports directory
            export_dir = Path("exports")
            export_dir.mkdir(exist_ok=True)

            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = {"json": "json", "text": "txt", "markdown": "md"}[format_type]
            verbose_suffix = "_verbose" if verbose else ""
            filename = export_dir / f"conversation_{timestamp}{verbose_suffix}.{ext}"

            # Write to file
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content)
                console.print(f"✓ Conversation history exported to: {filename}{verbose_label}", style="green")
            except Exception as e:
                console.print(f"❌ Failed to export: {e}", style="red")

    else:
        console.print(f"Unknown command: {command_text}. Type /help for available commands.", style="red")

    return True


async def _consume_wire(
    ui_side,
    console: Console,
    session: PromptSession,
) -> None:
    """Consume Wire messages and render them to the CLI.

    Handles ApprovalRequests inline by prompting the user.
    Runs as a background asyncio task alongside agent.run().
    """
    try:
        while True:
            msg = await ui_side.receive()

            if isinstance(msg, TextDelta):
                console.print(msg.text, end="")

            elif isinstance(msg, ToolCallEvent):
                inline = _format_tool_call_inline(msg.name, msg.arguments)
                console.print(f"  {inline}", style="cyan", markup=False)

            elif isinstance(msg, ToolResultEvent):
                style = "green" if msg.success else "red"
                icon = "✓" if msg.success else "✗"
                summary = _summarize_tool_result(msg.name, msg.result)
                console.print(f"  {icon} {msg.name}: {summary}", style=style, markup=False)

            elif isinstance(msg, ApprovalRequest):
                console.print(
                    f"\n🛡️ Approval required ({len(msg.tool_calls)} tool call(s)):",
                    style="bold cyan",
                )
                for tc in msg.tool_calls:
                    args = dict(tc.arguments) if tc.arguments else {}
                    preview = _format_tool_call_approval_inline(tc.name, args)
                    console.print(f"  {preview}", style="cyan", markup=False)

                console.print("\n  [1] ✅ Approve", style="green")
                console.print("  [2] ✅ Approve all (don't ask again)", style="green")
                console.print("  [3] ❌ Reject", style="red")

                choice = await session.prompt_async("\n> ")
                msg.resolve(_parse_approval_choice(choice))

            elif isinstance(msg, TurnEnd):
                break

    except QueueShutDown:
        pass


async def run_interactive(
    agent: Union[ResumeAgent, OrchestratorAgent],
    session_manager: Optional[SessionManager] = None,
    stream_enabled_default: bool = True,
):
    """Run interactive chat loop."""
    # Setup prompt with history
    history_file = Path.home() / ".resume_agent_history"
    session = PromptSession(
        history=FileHistory(str(history_file)),
        completer=ResumeCLICompleter(session_manager=session_manager),
        complete_while_typing=False,
    )
    runtime_options: Dict[str, Any] = {
        "stream_enabled": bool(stream_enabled_default),
    }

    print_banner()

    # Show mode
    from resume_agent.core.agent_factory import AutoAgent

    if isinstance(agent, OrchestratorAgent):
        console.print("🤖 Running in multi-agent mode", style="dim")
    elif isinstance(agent, AutoAgent):
        console.print("🤖 Running in auto-routing mode (single + multi-agent)", style="dim")
    else:
        console.print("🤖 Running in single-agent mode", style="dim")
    console.print("✅ Inline write approval enabled — file writes prompt before execution", style="green")
    console.print(
        f"✅ Streaming {'ON' if runtime_options['stream_enabled'] else 'OFF'} — use /stream [on|off|status]",
        style="green" if runtime_options["stream_enabled"] else "yellow",
    )

    while True:
        try:
            # Get user input — show pending approvals count if any
            prompt_prefix = "\n📝 You: "
            user_input = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: session.prompt(prompt_prefix),
            )

            user_input = user_input.strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.startswith("/"):
                should_continue = await handle_command(
                    user_input,
                    agent,
                    session_manager,
                    runtime_options=runtime_options,
                )
                if not should_continue:
                    break
                continue

            # Run agent with Wire protocol
            console.print("\n🤔 Thinking... (Press Ctrl+C to interrupt)", style="dim")
            agent_task = None
            consumer_task = None
            wire = None

            try:
                stream_enabled = bool(runtime_options.get("stream_enabled", False))

                wire = Wire()
                ui_side = wire.ui_side()
                consumer_task = asyncio.create_task(_consume_wire(ui_side, console, session))

                agent_task = asyncio.create_task(
                    agent.run(
                        user_input,
                        stream=stream_enabled,
                        wire=wire,
                    )
                )
                response = await agent_task

                console.print()
                if response.startswith("Error:"):
                    console.print(Panel(Markdown(response), title="🤖 Assistant", border_style="red"))
                else:
                    console.print(Panel(Markdown(response), title="🤖 Assistant", border_style="green"))

            except KeyboardInterrupt:
                if agent_task is not None and not agent_task.done():
                    agent_task.cancel()
                    try:
                        await agent_task
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        pass
                console.print("\n⚠️ Interrupted.", style="yellow")
            except Exception as e:
                console.print(f"\n❌ Error: {str(e)}", style="red")
            finally:
                if wire is not None:
                    wire.shutdown()
                if consumer_task is not None:
                    if not consumer_task.done():
                        consumer_task.cancel()
                    await asyncio.gather(consumer_task, return_exceptions=True)

        except KeyboardInterrupt:
            console.print("\n\n👋 Goodbye!", style="yellow")
            break
        except EOFError:
            console.print("\n👋 Goodbye!", style="yellow")
            break


def main():
    """Main entry point."""
    import argparse

    from dotenv import load_dotenv

    # Load environment variables from .env file
    load_dotenv()

    parser = argparse.ArgumentParser(description="Resume Agent - AI-powered resume modification assistant")
    parser.add_argument(
        "--workspace",
        "-w",
        default=".",
        help="Workspace directory for resume files (default: current directory)",
    )
    parser.add_argument(
        "--config",
        "-c",
        default="config/config.local.yaml",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--prompt",
        "-p",
        help="Run a single prompt and exit (non-interactive mode)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Verbose output (show tool executions, session summary, cache stats)",
    )
    parser.add_argument(
        "--multi-agent",
        "-m",
        action="store_true",
        help="Force multi-agent mode (overrides config)",
    )
    parser.add_argument(
        "--single-agent",
        "-s",
        action="store_true",
        help="Force single-agent mode (overrides config)",
    )
    parser.add_argument(
        "--stream",
        dest="stream",
        action="store_true",
        help="Enable streaming output (interactive default is off)",
    )
    parser.add_argument(
        "--no-stream",
        dest="stream",
        action="store_false",
        help="Disable streaming output",
    )
    parser.set_defaults(stream=None)

    args = parser.parse_args()

    # Load config
    try:
        llm_config = load_config(args.config)
    except FileNotFoundError:
        console.print(f"⚠️ Config file not found: {args.config}", style="yellow")
        console.print("Using default configuration. Set GEMINI_API_KEY environment variable.", style="dim")

        # Try to get API key from environment
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""

        llm_config = LLMConfig(
            api_key=api_key,
            model="gemini-2.5-flash" if os.environ.get("GEMINI_API_KEY") else "gpt-4o",
        )

    # Validate configuration at startup
    try:
        raw_config = load_raw_config(args.config)
    except FileNotFoundError:
        raw_config = {}

    issues = validate_config(raw_config, workspace_dir=args.workspace)
    if issues:
        for issue in issues:
            icon = "❌" if issue.severity == Severity.ERROR else "⚠️"
            style = "red" if issue.severity == Severity.ERROR else "yellow"
            console.print(f"  {icon} [{issue.field}] {issue.message}", style=style)

        if has_errors(issues):
            console.print(
                "\n💡 Fix the errors above, then try again.\n"
                "   Quick fix: export GEMINI_API_KEY=your_key_here\n"
                "   Or copy config/config.yaml → config/config.local.yaml and set api_key",
                style="dim",
            )
            return

    # Determine agent mode
    if args.single_agent:
        # Force single-agent mode
        agent_config = AgentConfig(
            workspace_dir=args.workspace,
            verbose=args.verbose,
        )
        session_manager = SessionManager(args.workspace)
        tools = create_tools(args.workspace, raw_config=raw_config)
        agent = ResumeAgent(
            llm_config=llm_config, agent_config=agent_config, session_manager=session_manager, tools=tools
        )
    elif args.multi_agent:
        # Force multi-agent mode
        session_manager = SessionManager(args.workspace)
        tools = create_tools(args.workspace, raw_config=raw_config)
        agent = create_agent(
            llm_config=llm_config,
            workspace_dir=args.workspace,
            session_manager=session_manager,
            verbose=args.verbose,
            tools=tools,
        )
        # Ensure it's multi-agent
        if isinstance(agent, ResumeAgent):
            console.print("⚠️ Multi-agent mode requested but not configured. Using single-agent.", style="yellow")
    else:
        # Use config to determine mode (single, multi, or auto)
        session_manager = SessionManager(args.workspace)
        tools = create_tools(args.workspace, raw_config=raw_config)
        agent = create_agent(
            llm_config=llm_config,
            workspace_dir=args.workspace,
            session_manager=session_manager,
            verbose=args.verbose,
            tools=tools,
        )

    # Run
    if args.prompt:
        # Non-interactive mode
        async def run_once():
            stream_enabled = bool(args.stream) if args.stream is not None else False

            response = await agent.run(
                args.prompt,
                stream=stream_enabled,
            )
            if response.startswith("Error:"):
                console.print(Panel(Markdown(response), title="🤖 Assistant", border_style="red"))
            else:
                console.print(Panel(Markdown(response), title="🤖 Assistant", border_style="green"))

            pending = _list_pending_tool_calls(agent)
            if pending:
                console.print(
                    f"\n⚠️ {len(pending)} pending tool call(s) require approval. "
                    "Run in interactive mode for inline approval.",
                    style="yellow",
                )

        asyncio.run(run_once())
    else:
        # Interactive mode
        interactive_stream_default = False if args.stream is None else bool(args.stream)
        asyncio.run(
            run_interactive(
                agent,
                session_manager,
                stream_enabled_default=interactive_stream_default,
            )
        )


if __name__ == "__main__":
    main()
