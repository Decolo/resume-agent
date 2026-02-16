"""Test verbose export functionality."""

from unittest.mock import Mock

import pytest

from packages.core.resume_agent_core.observability import AgentObserver


@pytest.fixture
def mock_agent():
    """Create a mock agent with history and observability data."""
    # Create mock agent
    agent = Mock()
    agent.agent = Mock()

    # Create real observer with events
    observer = AgentObserver(agent_id="test-agent")
    observer.log_tool_call(
        tool_name="file_read",
        args={"path": "test.txt"},
        result="File content",
        duration_ms=50.0,
        success=True,
        cached=False,
    )
    observer.log_llm_request(
        model="gemini-2.5-flash",
        tokens=100,
        cost=0.001,
        duration_ms=200.0,
        step=1,
    )

    # Create mock history
    mock_history = []

    # Mock user message
    user_msg = Mock()
    user_msg.role = "user"
    user_msg.parts = [Mock(text="Hello", function_call=None, function_response=None)]
    mock_history.append(user_msg)

    # Mock assistant message
    assistant_msg = Mock()
    assistant_msg.role = "assistant"
    assistant_msg.parts = [Mock(text="Hi there!", function_call=None, function_response=None)]
    mock_history.append(assistant_msg)

    # Setup agent mocks
    agent.agent.observer = observer
    agent.agent.history_manager = Mock()
    agent.agent.history_manager.get_history = Mock(return_value=mock_history)

    return agent


def test_export_has_observability_events(mock_agent):
    """Test that observability events are accessible."""
    observer = mock_agent.agent.observer
    assert len(observer.events) > 0

    # Check event types
    event_types = [e.event_type for e in observer.events]
    assert "tool_call" in event_types
    assert "llm_request" in event_types


def test_export_session_stats(mock_agent):
    """Test that session stats are calculated correctly."""
    observer = mock_agent.agent.observer
    stats = observer.get_session_stats()

    assert stats["tool_calls"] == 1
    assert stats["llm_requests"] == 1
    assert stats["total_tokens"] == 100
    assert stats["total_cost_usd"] == 0.001
    assert stats["errors"] == 0


def test_export_markdown_verbose_format(mock_agent):
    """Test markdown format with verbose observability logs."""
    observer = mock_agent.agent.observer
    history = mock_agent.agent.history_manager.get_history()

    # Simulate markdown export with verbose
    lines = ["# Conversation History\n"]

    for msg in history:
        if msg.role == "user":
            lines.append("## 👤 User\n")
        elif msg.role == "assistant":
            lines.append("## 🤖 Assistant\n")

        if msg.parts:
            for part in msg.parts:
                if hasattr(part, "text") and part.text:
                    lines.append(part.text + "\n")

        lines.append("---\n")

    # Add observability logs
    lines.append("\n# Observability Logs\n")

    for event in observer.events:
        timestamp = event.timestamp.strftime("%H:%M:%S")

        if event.event_type == "tool_call":
            tool = event.data.get("tool", "unknown")
            success = "✓" if event.data.get("success") else "✗"
            lines.append(f"- **[{timestamp}]** {success} Tool: `{tool}` ({event.duration_ms:.2f}ms)")

        elif event.event_type == "llm_request":
            model = event.data.get("model")
            step = event.data.get("step")
            lines.append(f"- **[{timestamp}]** 🤖 LLM Request: `{model}` (Step {step})")

    # Add session stats
    stats = observer.get_session_stats()
    lines.append("\n## Session Statistics\n")
    lines.append(f"- **Total Events:** {stats['event_count']}")
    lines.append(f"- **Tool Calls:** {stats['tool_calls']}")
    lines.append(f"- **LLM Requests:** {stats['llm_requests']}")

    content = "\n".join(lines)

    # Verify content
    assert "# Conversation History" in content
    assert "# Observability Logs" in content
    assert "## Session Statistics" in content
    assert "Tool: `file_read`" in content
    assert "LLM Request: `gemini-2.5-flash`" in content
    assert "Total Events:" in content


def test_export_json_verbose_format(mock_agent):
    """Test JSON format with verbose observability data."""
    import json
    from datetime import datetime

    observer = mock_agent.agent.observer
    history = mock_agent.agent.history_manager.get_history()

    # Simulate JSON export with verbose
    export_data = {"exported_at": datetime.now().isoformat(), "agent_mode": "single-agent", "messages": []}

    for msg in history:
        msg_data = {"role": msg.role, "parts": []}
        if msg.parts:
            for part in msg.parts:
                if hasattr(part, "text") and part.text:
                    msg_data["parts"].append({"type": "text", "content": part.text})
        export_data["messages"].append(msg_data)

    # Add observability data
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
            for event in observer.events
        ],
        "session_stats": observer.get_session_stats(),
    }

    content = json.dumps(export_data, indent=2)
    data = json.loads(content)

    # Verify structure
    assert "messages" in data
    assert "observability" in data
    assert "events" in data["observability"]
    assert "session_stats" in data["observability"]
    assert len(data["observability"]["events"]) == 2
    assert data["observability"]["session_stats"]["tool_calls"] == 1
    assert data["observability"]["session_stats"]["llm_requests"] == 1


def test_export_text_verbose_format(mock_agent):
    """Test plain text format with verbose observability logs."""
    observer = mock_agent.agent.observer
    history = mock_agent.agent.history_manager.get_history()

    # Simulate text export with verbose
    lines = []

    for msg in history:
        role_label = "User" if msg.role == "user" else "Assistant"
        lines.append(f"\n{'=' * 60}")
        lines.append(f"{role_label}:")
        lines.append("=" * 60)

        if msg.parts:
            for part in msg.parts:
                if hasattr(part, "text") and part.text:
                    lines.append(part.text)

    # Add observability logs
    lines.append(f"\n\n{'=' * 60}")
    lines.append("OBSERVABILITY LOGS")
    lines.append("=" * 60)

    for event in observer.events:
        lines.append(f"\n[{event.timestamp.strftime('%H:%M:%S')}] {event.event_type.upper()}")

        if event.event_type == "tool_call":
            tool = event.data.get("tool", "unknown")
            success = "✓" if event.data.get("success") else "✗"
            lines.append(f"  {success} Tool: {tool} ({event.duration_ms:.2f}ms)")

        elif event.event_type == "llm_request":
            lines.append(f"  Model: {event.data.get('model')}")
            lines.append(f"  Tokens: {event.tokens_used}")

    # Add session stats
    stats = observer.get_session_stats()
    lines.append(f"\n{'=' * 60}")
    lines.append("SESSION STATISTICS")
    lines.append("=" * 60)
    lines.append(f"Total Events:     {stats['event_count']}")
    lines.append(f"Tool Calls:       {stats['tool_calls']}")

    content = "\n".join(lines)

    # Verify content
    assert "OBSERVABILITY LOGS" in content
    assert "SESSION STATISTICS" in content
    assert "Tool: file_read" in content
    assert "Model: gemini-2.5-flash" in content
    assert "Total Events:" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
