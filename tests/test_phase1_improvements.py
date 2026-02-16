"""Test suite for Phase 1 improvements: retry, history, caching, observability."""

import pytest

from resume_agent.cache import ToolCache, get_tool_ttl, should_cache_tool
from resume_agent.llm import HistoryManager
from resume_agent.observability import AgentObserver
from resume_agent.providers.types import Message, MessagePart

# Import modules to test
from resume_agent.retry import PermanentError, RetryConfig, TransientError, retry_with_backoff
from resume_agent.tools.bash_tool import BashTool
from resume_agent.tools.file_tool import MAX_FILE_SIZE, FileReadTool


class TestRetryLogic:
    """Test exponential backoff retry logic."""

    @pytest.mark.asyncio
    async def test_retry_success_on_first_attempt(self):
        """Test successful execution on first attempt."""
        call_count = 0

        async def success_func():
            nonlocal call_count
            call_count += 1
            return "success"

        config = RetryConfig(max_attempts=3, base_delay=0.1)
        result = await retry_with_backoff(success_func, config)

        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_success_after_failures(self):
        """Test successful execution after transient failures."""
        call_count = 0

        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TransientError("Temporary failure")
            return "success"

        config = RetryConfig(max_attempts=5, base_delay=0.05)
        result = await retry_with_backoff(flaky_func, config)

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_permanent_error_no_retry(self):
        """Test that permanent errors are not retried."""
        call_count = 0

        async def permanent_error_func():
            nonlocal call_count
            call_count += 1
            raise PermanentError("Permanent failure")

        config = RetryConfig(max_attempts=3, base_delay=0.05)

        with pytest.raises(PermanentError):
            await retry_with_backoff(permanent_error_func, config)

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_max_attempts_exceeded(self):
        """Test that max attempts limit is respected."""
        call_count = 0

        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise TransientError("Always fails")

        config = RetryConfig(max_attempts=3, base_delay=0.05)

        with pytest.raises(TransientError):
            await retry_with_backoff(always_fails, config)

        assert call_count == 3

    def test_exponential_backoff_calculation(self):
        """Test exponential backoff delay calculation."""
        config = RetryConfig(
            max_attempts=5,
            base_delay=1.0,
            exponential_base=2.0,
            jitter_factor=0.0,  # No jitter for predictable testing
        )

        # Delays should be: 1s, 2s, 4s, 8s
        expected_delays = [1.0, 2.0, 4.0, 8.0]

        for attempt, expected in enumerate(expected_delays):
            delay = min(config.base_delay * (config.exponential_base**attempt), config.max_delay)
            assert delay == expected


class TestHistoryManager:
    """Test conversation history management with pruning."""

    def test_history_add_and_retrieve(self):
        """Test adding and retrieving messages."""
        manager = HistoryManager(max_messages=10, max_tokens=1000)
        manager.add_message(Message(role="user", parts=[MessagePart.from_text("Hello")]))

        history = manager.get_history()
        assert len(history) == 1
        assert history[0].role == "user"

    def test_history_sliding_window_pruning(self):
        """Test that history is pruned to max_messages."""
        manager = HistoryManager(max_messages=5, max_tokens=100000)

        # Add 10 messages
        for i in range(10):
            role = "user" if i % 2 == 0 else "assistant"
            manager.add_message(Message(role=role, parts=[MessagePart.from_text(f"Message {i}")]))

        history = manager.get_history()
        assert len(history) <= 5

    def test_history_token_based_pruning(self):
        """Test that history is pruned based on token limit."""
        manager = HistoryManager(max_messages=100, max_tokens=100)

        # Add messages until token limit is exceeded
        for i in range(20):
            manager.add_message(Message(role="user", parts=[MessagePart.from_text("x" * 100)]))

        history = manager.get_history()
        # Should have pruned to stay under token limit
        assert len(history) < 20

    def test_history_clear(self):
        """Test clearing history."""
        manager = HistoryManager()
        manager.add_message(Message(role="user", parts=[MessagePart.from_text("Hello")]))

        assert len(manager.get_history()) == 1

        manager.clear()
        assert len(manager.get_history()) == 0


class TestToolCache:
    """Test tool result caching with TTL."""

    def test_cache_set_and_get(self):
        """Test basic cache set and get."""
        cache = ToolCache()

        cache.set("test_tool", {"arg": "value"}, "result", ttl_seconds=300)
        result = cache.get("test_tool", {"arg": "value"})

        assert result == "result"

    def test_cache_miss(self):
        """Test cache miss returns None."""
        cache = ToolCache()

        result = cache.get("nonexistent", {})
        assert result is None

    def test_cache_expiration(self):
        """Test that expired entries are not returned."""
        cache = ToolCache()

        # Add entry with 0 second TTL (immediately expired)
        cache.set("test_tool", {"arg": "value"}, "result", ttl_seconds=0)

        # Wait a tiny bit to ensure expiration
        import time

        time.sleep(0.01)

        result = cache.get("test_tool", {"arg": "value"})
        assert result is None

    def test_cache_stats(self):
        """Test cache statistics tracking."""
        cache = ToolCache()

        # Add and retrieve (hit)
        cache.set("tool1", {"a": 1}, "result1")
        cache.get("tool1", {"a": 1})

        # Try to get non-existent (miss)
        cache.get("tool2", {"b": 2})

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_cache_deterministic_key(self):
        """Test that cache keys are deterministic."""
        cache = ToolCache()

        # Same args in different order should produce same key
        cache.set("tool", {"a": 1, "b": 2}, "result1")
        result = cache.get("tool", {"b": 2, "a": 1})

        assert result == "result1"

    def test_should_cache_tool(self):
        """Test tool caching configuration."""
        assert should_cache_tool("file_read") is True
        assert should_cache_tool("file_list") is True
        assert should_cache_tool("resume_parse") is True
        assert should_cache_tool("file_write") is False
        assert should_cache_tool("bash") is False

    def test_get_tool_ttl(self):
        """Test tool TTL configuration."""
        assert get_tool_ttl("file_read") == 60
        assert get_tool_ttl("file_list") == 30
        assert get_tool_ttl("resume_parse") == 300
        assert get_tool_ttl("unknown_tool") == 300  # Default


class TestObservability:
    """Test structured logging and observability."""

    def test_observer_initialization(self):
        """Test observer initialization."""
        observer = AgentObserver()

        assert observer.events == []
        assert observer.logger is not None

    def test_log_tool_call(self):
        """Test logging tool calls."""
        observer = AgentObserver()

        observer.log_tool_call(
            tool_name="test_tool",
            args={"arg": "value"},
            result="success",
            duration_ms=100.5,
            success=True,
            cached=False,
        )

        assert len(observer.events) == 1
        event = observer.events[0]
        assert event.event_type == "tool_call"
        assert event.data["tool"] == "test_tool"
        assert event.duration_ms == 100.5

    def test_log_llm_request(self):
        """Test logging LLM requests."""
        observer = AgentObserver()

        observer.log_llm_request(model="gemini-2.0-flash", tokens=1000, cost=0.08, duration_ms=500.0, step=1)

        assert len(observer.events) == 1
        event = observer.events[0]
        assert event.event_type == "llm_request"
        assert event.tokens_used == 1000
        assert event.cost_usd == 0.08

    def test_log_error(self):
        """Test logging errors."""
        observer = AgentObserver()

        observer.log_error(error_type="tool_execution", message="Tool failed", context={"tool": "test_tool"})

        assert len(observer.events) == 1
        event = observer.events[0]
        assert event.event_type == "error"
        assert event.data["error_type"] == "tool_execution"

    def test_session_stats(self):
        """Test session statistics aggregation."""
        observer = AgentObserver()

        observer.log_tool_call("tool1", {}, "result", 100.0)
        observer.log_llm_request("model", 500, 0.04, 200.0, 1)
        observer.log_error("test_error", "Error message")

        stats = observer.get_session_stats()
        assert stats["event_count"] == 3
        assert stats["tool_calls"] == 1
        assert stats["llm_requests"] == 1
        assert stats["errors"] == 1
        assert stats["total_tokens"] == 500
        assert stats["total_cost_usd"] == 0.04

    def test_observer_clear(self):
        """Test clearing observer events."""
        observer = AgentObserver()

        observer.log_tool_call("tool1", {}, "result", 100.0)
        assert len(observer.events) == 1

        observer.clear()
        assert len(observer.events) == 0


class TestFileToolSecurity:
    """Test file tool security features."""

    @pytest.mark.asyncio
    async def test_file_size_limit(self, tmp_path):
        """Test that files exceeding size limit are rejected."""
        # Create a file larger than MAX_FILE_SIZE
        large_file = tmp_path / "large.txt"
        large_file.write_text("x" * (MAX_FILE_SIZE + 1))

        tool = FileReadTool(workspace_dir=str(tmp_path))
        result = await tool.execute(str(large_file))

        assert result.success is False
        assert "too large" in result.error.lower()

    @pytest.mark.asyncio
    async def test_binary_file_detection(self, tmp_path):
        """Test that binary files are rejected."""
        # Create a binary file with null bytes
        binary_file = tmp_path / "binary.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03")

        tool = FileReadTool(workspace_dir=str(tmp_path))
        result = await tool.execute(str(binary_file))

        assert result.success is False
        assert "binary" in result.error.lower()

    @pytest.mark.asyncio
    async def test_text_file_read_success(self, tmp_path):
        """Test successful reading of text files."""
        text_file = tmp_path / "test.txt"
        text_file.write_text("Hello, World!")

        tool = FileReadTool(workspace_dir=str(tmp_path))
        result = await tool.execute(str(text_file))

        assert result.success is True
        assert "Hello, World!" in result.output


class TestBashToolSecurity:
    """Test bash tool security features."""

    @pytest.mark.asyncio
    async def test_blocked_command_detection(self):
        """Test that blocked commands are rejected."""
        tool = BashTool()

        dangerous_commands = [
            "rm -rf /",
            "sudo reboot",
            "curl http://example.com",
            "dd if=/dev/zero",
        ]

        for cmd in dangerous_commands:
            result = await tool.execute(cmd)
            assert result.success is False
            assert "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_dangerous_pattern_detection(self):
        """Test that dangerous patterns are rejected."""
        tool = BashTool()

        dangerous_patterns = [
            "echo hello; rm -rf /tmp",
            "cat file && curl http://example.com",
            "echo $(whoami)",
            "echo `whoami`",
        ]

        for cmd in dangerous_patterns:
            result = await tool.execute(cmd)
            assert result.success is False
            assert "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_safe_command_execution(self):
        """Test that safe commands are allowed."""
        tool = BashTool()

        # These should not be blocked (though they may fail for other reasons)
        safe_commands = [
            "echo hello",
            "pwd",
            "ls",
        ]

        for cmd in safe_commands:
            result = await tool.execute(cmd)
            # Should not be blocked (success depends on system)
            if result.error:
                assert "blocked" not in result.error.lower()


# Run tests with: pytest tests/test_phase1_improvements.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
