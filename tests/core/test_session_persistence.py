"""Tests for session persistence functionality."""

import pytest

from resume_agent.core.llm import HistoryManager, LLMAgent, LLMConfig
from resume_agent.core.observability import AgentObserver
from resume_agent.core.session import (
    SessionIndex,
    SessionManager,
    SessionSerializer,
)
from resume_agent.providers.types import FunctionCall, FunctionResponse, Message, MessagePart


class TestSessionSerializer:
    """Test session serialization and deserialization."""

    def test_serialize_text_message(self):
        """Test serializing a text message."""
        msg = Message(role="user", parts=[MessagePart.from_text("Hello, world!")])

        serialized = SessionSerializer.serialize_message(msg)

        assert serialized["role"] == "user"
        assert len(serialized["parts"]) == 1
        assert serialized["parts"][0]["type"] == "text"
        assert serialized["parts"][0]["content"] == "Hello, world!"

    def test_serialize_function_call(self):
        """Test serializing a function call message."""
        msg = Message(
            role="assistant",
            parts=[MessagePart.from_function_call(FunctionCall(name="file_read", arguments={"file_path": "test.txt"}))],
        )

        serialized = SessionSerializer.serialize_message(msg)

        assert serialized["role"] == "assistant"
        assert len(serialized["parts"]) == 1
        assert serialized["parts"][0]["type"] == "function_call"
        assert serialized["parts"][0]["name"] == "file_read"
        assert serialized["parts"][0]["args"]["file_path"] == "test.txt"

    def test_serialize_function_response(self):
        """Test serializing a function response message."""
        msg = Message(
            role="tool",
            parts=[
                MessagePart.from_function_response(
                    FunctionResponse(name="file_read", response={"result": "File contents"})
                )
            ],
        )

        serialized = SessionSerializer.serialize_message(msg)

        assert serialized["role"] == "tool"
        assert len(serialized["parts"]) == 1
        assert serialized["parts"][0]["type"] == "function_response"
        assert serialized["parts"][0]["name"] == "file_read"

    def test_deserialize_text_message(self):
        """Test deserializing a text message."""
        data = {"role": "user", "parts": [{"type": "text", "content": "Hello, world!"}]}

        msg = SessionSerializer.deserialize_message(data)

        assert msg.role == "user"
        assert len(msg.parts) == 1
        assert msg.parts[0].text == "Hello, world!"

    def test_deserialize_function_call(self):
        """Test deserializing a function call message."""
        data = {
            "role": "assistant",
            "parts": [{"type": "function_call", "name": "file_read", "args": {"file_path": "test.txt"}}],
        }

        msg = SessionSerializer.deserialize_message(data)

        assert msg.role == "assistant"
        assert len(msg.parts) == 1
        assert msg.parts[0].function_call.name == "file_read"
        assert dict(msg.parts[0].function_call.arguments)["file_path"] == "test.txt"

    def test_serialize_history(self):
        """Test serializing conversation history."""
        history_manager = HistoryManager(max_messages=50, max_tokens=100000)
        history_manager.add_message(Message(role="user", parts=[MessagePart.from_text("Hello")]))
        history_manager.add_message(Message(role="assistant", parts=[MessagePart.from_text("Hi there!")]))

        serialized = SessionSerializer.serialize_history(history_manager)

        assert serialized["history_format"] == "turn_tree_v1"
        assert len(serialized["turns"]) == 1
        assert serialized["max_messages"] == 50
        assert serialized["max_tokens"] == 100000

    def test_restore_history_manager_from_turn_tree_payload(self):
        """Test restoring history manager from serialized turn-tree history."""
        original = HistoryManager(max_messages=50, max_tokens=100000)
        original.add_message(Message(role="user", parts=[MessagePart.from_text("Hello")]))
        original.add_message(Message(role="assistant", parts=[MessagePart.from_text("Hi there!")]))
        data = SessionSerializer.serialize_history(original)

        restored = HistoryManager(max_messages=1, max_tokens=1)
        SessionSerializer.restore_history_manager(restored, data)

        messages = restored.get_history()
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].parts[0].text == "Hello"
        assert messages[1].role == "assistant"
        assert messages[1].parts[0].text == "Hi there!"

    def test_restore_history_manager_keeps_current_runtime_token_budget(self):
        """Restoring a session should not overwrite the current model token budget."""
        original = HistoryManager(max_messages=50, max_tokens=100000, reserve_tokens=2048)
        original.add_message(Message(role="user", parts=[MessagePart.from_text("Hello")]))
        original.add_message(Message(role="assistant", parts=[MessagePart.from_text("Hi there!")]))
        data = SessionSerializer.serialize_history(original)

        restored = HistoryManager(max_messages=50, max_tokens=128000, reserve_tokens=4096)
        SessionSerializer.restore_history_manager(restored, data)

        assert restored.max_tokens == 128000
        assert restored.reserve_tokens == 4096
        assert len(restored.get_history()) == 2

    def test_restore_history_manager_rejects_legacy_linear_history_payload(self):
        """Legacy sessions without turn-tree metadata should be rejected clearly."""
        restored = HistoryManager(max_messages=50, max_tokens=100000)
        restored.add_message(Message(role="user", parts=[MessagePart.from_text("Keep this message")]))
        restored.add_message(Message(role="assistant", parts=[MessagePart.from_text("Still active")]))

        with pytest.raises(ValueError, match="/clear-sessions"):
            SessionSerializer.restore_history_manager(
                restored,
                {
                    "messages": [
                        {"role": "user", "parts": [{"type": "text", "content": "Hello"}]},
                    ],
                    "max_messages": 50,
                    "max_tokens": 100000,
                },
            )

        messages = restored.get_history()
        assert len(messages) == 2
        assert messages[0].parts[0].text == "Keep this message"
        assert messages[1].parts[0].text == "Still active"

    def test_serialize_observability(self):
        """Test serializing observability data."""
        observer = AgentObserver(agent_id="test_agent")
        observer.log_tool_call(
            tool_name="file_read",
            args={"file_path": "test.txt"},
            result="File contents",
            duration_ms=100.0,
            success=True,
            cached=False,
        )

        serialized = SessionSerializer.serialize_observability(observer)

        assert "events" in serialized
        assert "session_stats" in serialized
        assert len(serialized["events"]) == 1
        assert serialized["events"][0]["event_type"] == "tool_call"

    def test_deserialize_observability(self):
        """Test deserializing observability data."""
        data = {
            "events": [
                {
                    "timestamp": "2026-02-02T14:30:00",
                    "event_type": "tool_call",
                    "data": {"tool": "file_read"},
                    "duration_ms": 100.0,
                    "tokens_used": None,
                    "cost_usd": None,
                }
            ]
        }

        events = SessionSerializer.deserialize_observability(data)

        assert len(events) == 1
        assert events[0].event_type == "tool_call"
        assert events[0].data["tool"] == "file_read"


class TestSessionIndex:
    """Test session index functionality."""

    def test_add_session_makes_metadata_available_for_later_lookup(self, tmp_path):
        """Test adding and retrieving session metadata."""
        index_path = tmp_path / ".index.json"
        index = SessionIndex(index_path)

        metadata = {
            "created_at": "2026-02-02T14:30:00",
            "updated_at": "2026-02-02T14:30:00",
            "mode": "single-agent",
            "message_count": 10,
            "total_tokens": 1000,
            "total_cost_usd": 0.01,
        }

        index.add_session("test_session_123", metadata)

        retrieved = index.get_session_metadata("test_session_123")
        assert retrieved is not None
        assert retrieved["mode"] == "single-agent"
        assert retrieved["message_count"] == 10

    def test_remove_session_deletes_metadata_from_the_index(self, tmp_path):
        """Test removing session from index."""
        index_path = tmp_path / ".index.json"
        index = SessionIndex(index_path)

        metadata = {
            "created_at": "2026-02-02T14:30:00",
            "updated_at": "2026-02-02T14:30:00",
            "mode": "single-agent",
            "message_count": 10,
            "total_tokens": 1000,
            "total_cost_usd": 0.01,
        }

        index.add_session("test_session_123", metadata)
        index.remove_session("test_session_123")

        retrieved = index.get_session_metadata("test_session_123")
        assert retrieved is None

    def test_list_all_returns_sessions_sorted_by_most_recent_update(self, tmp_path):
        """Test listing all sessions."""
        index_path = tmp_path / ".index.json"
        index = SessionIndex(index_path)

        # Add multiple sessions
        for i in range(3):
            metadata = {
                "created_at": f"2026-02-02T14:3{i}:00",
                "updated_at": f"2026-02-02T14:3{i}:00",
                "mode": "single-agent",
                "message_count": 10 + i,
                "total_tokens": 1000 + i * 100,
                "total_cost_usd": 0.01 + i * 0.001,
            }
            index.add_session(f"test_session_{i}", metadata)

        sessions = index.list_all()
        assert len(sessions) == 3
        # Should be sorted by updated_at (most recent first)
        assert sessions[0]["id"] == "test_session_2"


class TestSessionManager:
    """Test session manager functionality."""

    def test_init_creates_missing_workspace_tree(self, tmp_path):
        """SessionManager should create workspace/sessions when workspace is missing."""
        workspace = tmp_path / "missing" / "workspace"
        assert not workspace.exists()

        session_manager = SessionManager(str(workspace))

        assert workspace.exists()
        assert workspace.is_dir()
        assert session_manager.sessions_dir.exists()
        assert session_manager.sessions_dir.is_dir()

    def test_save_and_load_session(self, tmp_path):
        """Test saving and loading a session."""
        # Create a mock agent with history
        config = LLMConfig(api_key="test_key", model="gemini-2.5-flash")
        agent = LLMAgent(config=config, system_prompt="Test prompt")

        # Add some history
        agent.history_manager.add_message(Message(role="user", parts=[MessagePart.from_text("Hello")]))
        agent.history_manager.add_message(Message(role="assistant", parts=[MessagePart.from_text("Hi there!")]))

        # Create a mock parent agent
        class MockAgent:
            def __init__(self):
                self.agent = agent
                self.llm_config = config
                self.agent_config = type("obj", (object,), {"workspace_dir": str(tmp_path)})()

        mock_agent = MockAgent()

        # Save session
        session_manager = SessionManager(str(tmp_path))
        session_id = session_manager.save_session(mock_agent)

        assert session_id is not None
        assert session_id.startswith("session_")

        # Load session
        session_data = session_manager.load_session(session_id)

        assert session_data["schema_version"] == "2.0"
        assert session_data["session"]["mode"] == "single-agent"
        assert session_data["conversation"]["history_format"] == "turn_tree_v1"
        assert len(session_data["conversation"]["turns"]) == 1

    def test_list_sessions_returns_each_saved_session_from_workspace_storage(self, tmp_path):
        """Test listing sessions."""
        config = LLMConfig(api_key="test_key", model="gemini-2.5-flash")
        agent = LLMAgent(config=config, system_prompt="Test prompt")

        class MockAgent:
            def __init__(self):
                self.agent = agent
                self.llm_config = config
                self.agent_config = type("obj", (object,), {"workspace_dir": str(tmp_path)})()

        mock_agent = MockAgent()

        session_manager = SessionManager(str(tmp_path))

        # Save multiple sessions
        session_ids = []
        for i in range(3):
            agent.history_manager.add_message(Message(role="user", parts=[MessagePart.from_text(f"Message {i}")]))
            session_id = session_manager.save_session(mock_agent)
            session_ids.append(session_id)

        # List sessions
        sessions = session_manager.list_sessions()
        assert len(sessions) == 3

    def test_delete_session_removes_the_saved_session_file_from_workspace_storage(self, tmp_path):
        """Test deleting a session."""
        config = LLMConfig(api_key="test_key", model="gemini-2.5-flash")
        agent = LLMAgent(config=config, system_prompt="Test prompt")

        class MockAgent:
            def __init__(self):
                self.agent = agent
                self.llm_config = config
                self.agent_config = type("obj", (object,), {"workspace_dir": str(tmp_path)})()

        mock_agent = MockAgent()

        session_manager = SessionManager(str(tmp_path))
        session_id = session_manager.save_session(mock_agent)

        # Delete session
        result = session_manager.delete_session(session_id)
        assert result is True

        # Verify it's gone
        with pytest.raises(FileNotFoundError):
            session_manager.load_session(session_id)

    def test_restore_agent_state(self, tmp_path):
        """Test restoring agent state from session."""
        config = LLMConfig(api_key="test_key", model="gemini-2.5-flash")
        agent = LLMAgent(config=config, system_prompt="Test prompt")

        # Add history
        agent.history_manager.add_message(Message(role="user", parts=[MessagePart.from_text("Hello")]))
        agent.history_manager.add_message(Message(role="assistant", parts=[MessagePart.from_text("Hi there!")]))

        class MockAgent:
            def __init__(self):
                self.agent = agent
                self.llm_config = config
                self.agent_config = type("obj", (object,), {"workspace_dir": str(tmp_path)})()

        mock_agent = MockAgent()

        # Save session
        session_manager = SessionManager(str(tmp_path))
        session_id = session_manager.save_session(mock_agent)

        # Create new agent and restore
        new_agent = LLMAgent(config=config, system_prompt="Test prompt")
        new_mock_agent = MockAgent()
        new_mock_agent.agent = new_agent

        session_data = session_manager.load_session(session_id)
        session_manager.restore_agent_state(new_mock_agent, session_data)

        # Verify history was restored
        restored_history = new_agent.history_manager.get_history()
        assert len(restored_history) == 2
        assert restored_history[0].role == "user"
        assert restored_history[0].parts[0].text == "Hello"
        assert restored_history[1].role == "assistant"
        assert restored_history[1].parts[0].text == "Hi there!"

    def test_clear_sessions_removes_all_saved_sessions(self, tmp_path):
        """Test clearing all saved sessions and resetting the index."""
        config = LLMConfig(api_key="test_key", model="gemini-2.5-flash")
        agent = LLMAgent(config=config, system_prompt="Test prompt")

        class MockAgent:
            def __init__(self):
                self.agent = agent
                self.llm_config = config
                self.agent_config = type("obj", (object,), {"workspace_dir": str(tmp_path)})()

        mock_agent = MockAgent()
        session_manager = SessionManager(str(tmp_path))

        session_manager.save_session(mock_agent)
        session_manager.save_session(mock_agent)

        removed = session_manager.clear_sessions()

        assert removed == 2
        assert session_manager.list_sessions() == []


def test_session_name_is_sanitized_for_filesystem(tmp_path):
    """Custom session names should not create nested paths or invalid filenames."""
    config = LLMConfig(api_key="test_key", model="gemini-2.5-flash")
    agent = LLMAgent(config=config, system_prompt="Test prompt")

    class MockAgent:
        def __init__(self):
            self.agent = agent
            self.llm_config = config
            self.agent_config = type("obj", (object,), {"workspace_dir": str(tmp_path)})()

    mock_agent = MockAgent()
    session_manager = SessionManager(str(tmp_path))

    session_id = session_manager.save_session(mock_agent, session_name="../My Session:V1")

    assert "/" not in session_id
    assert "\\" not in session_id
    assert "My_Session_V1" in session_id

    session_file = tmp_path / "sessions" / f"{session_id}.json"
    assert session_file.exists()
