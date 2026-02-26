"""Tests for multi-agent core components."""

from resume_agent.core.agents.context import SharedContext
from resume_agent.core.agents.protocol import (
    AgentResult,
    AgentTask,
    create_result,
    generate_task_id,
)


class TestAgentTask:
    """Tests for AgentTask dataclass."""

    def test_create_task_with_defaults(self):
        """Test creating a task with default values."""
        task = AgentTask(
            task_id="test_123",
            task_type="parse",
            description="Parse a resume",
        )

        assert task.task_id == "test_123"
        assert task.task_type == "parse"
        assert task.description == "Parse a resume"
        assert task.parameters == {}
        assert task.context == {}
        assert task.parent_task_id is None
        assert task.max_depth == 5

    def test_create_task_with_all_fields(self):
        """Test creating a task with all fields."""
        task = AgentTask(
            task_id="test_456",
            task_type="write",
            description="Improve content",
            parameters={"section": "experience"},
            context={"user_id": "123"},
            parent_task_id="parent_789",
            max_depth=3,
        )

        assert task.task_id == "test_456"
        assert task.parameters == {"section": "experience"}
        assert task.context == {"user_id": "123"}
        assert task.parent_task_id == "parent_789"
        assert task.max_depth == 3

    def test_generate_task_id(self):
        """Test that task IDs are unique."""
        id1 = generate_task_id()
        id2 = generate_task_id()

        assert id1 != id2
        assert id1.startswith("task_")
        assert id2.startswith("task_")


class TestAgentResult:
    """Tests for AgentResult dataclass."""

    def test_create_result_success(self):
        """Test creating a successful result."""
        result = AgentResult(
            task_id="task_123",
            agent_id="parser_agent",
            success=True,
            output="Parsed content",
            metadata={"sections": 3},
            execution_time_ms=150.5,
        )

        assert result.task_id == "task_123"
        assert result.agent_id == "parser_agent"
        assert result.success is True
        assert result.output == "Parsed content"
        assert result.metadata == {"sections": 3}
        assert result.execution_time_ms == 150.5
        assert result.error is None

    def test_create_result_failure(self):
        """Test creating a failed result."""
        result = AgentResult(
            task_id="task_456",
            agent_id="writer_agent",
            success=False,
            output="",
            error="File not found",
            execution_time_ms=50.0,
        )

        assert result.success is False
        assert result.error == "File not found"


class TestSharedContext:
    """Tests for SharedContext class."""

    def test_set_and_get(self):
        """Test setting and getting values."""
        context = SharedContext()

        context.set("key1", "value1", agent_id="agent1")
        context.set("key2", {"nested": "data"}, agent_id="agent2")

        assert context.get("key1") == "value1"
        assert context.get("key2") == {"nested": "data"}
        assert context.get("nonexistent") is None
        assert context.get("nonexistent", "default") == "default"

    def test_has_and_contains(self):
        """Test checking key existence."""
        context = SharedContext()
        context.set("key1", "value1")

        assert context.has("key1") is True
        assert context.has("key2") is False
        assert "key1" in context
        assert "key2" not in context

    def test_delete(self):
        """Test deleting values."""
        context = SharedContext()
        context.set("key1", "value1")

        deleted = context.delete("key1", agent_id="agent1")

        assert deleted == "value1"
        assert context.has("key1") is False
        assert context.delete("nonexistent") is None

    def test_history_tracking(self):
        """Test that updates are tracked in history."""
        context = SharedContext()

        context.set("key1", "value1", agent_id="agent1")
        context.set("key1", "value2", agent_id="agent2")

        history = context.get_history()
        assert len(history) == 2

        assert history[0].key == "key1"
        assert history[0].value == "value1"
        assert history[0].agent_id == "agent1"
        assert history[0].previous_value is None

        assert history[1].key == "key1"
        assert history[1].value == "value2"
        assert history[1].agent_id == "agent2"
        assert history[1].previous_value == "value1"

    def test_get_history_for_key(self):
        """Test getting history for a specific key."""
        context = SharedContext()

        context.set("key1", "v1")
        context.set("key2", "v2")
        context.set("key1", "v3")

        key1_history = context.get_history_for_key("key1")
        assert len(key1_history) == 2

    def test_get_history_by_agent(self):
        """Test getting history by agent."""
        context = SharedContext()

        context.set("key1", "v1", agent_id="agent1")
        context.set("key2", "v2", agent_id="agent2")
        context.set("key3", "v3", agent_id="agent1")

        agent1_history = context.get_history_by_agent("agent1")
        assert len(agent1_history) == 2

    def test_merge(self):
        """Test merging contexts."""
        context1 = SharedContext()
        context1.set("key1", "value1")
        context1.set("key2", "value2")

        context2 = SharedContext()
        context2.set("key2", "new_value2")
        context2.set("key3", "value3")

        context1.merge(context2, agent_id="merger")

        assert context1.get("key1") == "value1"
        assert context1.get("key2") == "new_value2"  # Overwritten
        assert context1.get("key3") == "value3"

    def test_copy(self):
        """Test copying context."""
        context = SharedContext()
        context.set("key1", "value1")

        copy = context.copy()

        assert copy.get("key1") == "value1"
        assert len(copy.get_history()) == 0  # History not copied

        # Verify independence
        copy.set("key2", "value2")
        assert context.has("key2") is False

    def test_to_dict(self):
        """Test converting to dictionary."""
        context = SharedContext()
        context.set("key1", "value1")
        context.set("key2", "value2")

        d = context.to_dict()

        assert d == {"key1": "value1", "key2": "value2"}

    def test_initial_data(self):
        """Test initializing with data."""
        context = SharedContext(initial_data={"key1": "value1", "key2": "value2"})

        assert context.get("key1") == "value1"
        assert context.get("key2") == "value2"
        assert len(context) == 2

    def test_clear(self):
        """Test clearing context."""
        context = SharedContext()
        context.set("key1", "value1")
        context.set("key2", "value2")

        context.clear()

        assert len(context) == 0
        assert len(context.get_history()) == 0


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_create_result_helper(self):
        """Test create_result helper function."""
        result = create_result(
            task_id="task_123",
            agent_id="parser",
            success=True,
            output="Parsed content",
            execution_time_ms=100.0,
            metadata={"sections": 3},
        )

        assert result.task_id == "task_123"
        assert result.agent_id == "parser"
        assert result.success is True
        assert result.output == "Parsed content"
        assert result.execution_time_ms == 100.0
        assert result.metadata == {"sections": 3}
