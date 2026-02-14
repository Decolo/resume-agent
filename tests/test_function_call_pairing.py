"""Tests for function call/response pairing in HistoryManager."""

import pytest

from resume_agent.llm import HistoryManager
from resume_agent.providers.types import FunctionCall, FunctionResponse, Message, MessagePart


def create_user_message(text: str) -> Message:
    """Create a user message."""
    return Message.user(text)


def create_model_message(text: str) -> Message:
    """Create an assistant message."""
    return Message(role="assistant", parts=[MessagePart.from_text(text)])


def create_function_call_message(func_name: str) -> Message:
    """Create an assistant message with function call."""
    return Message(
        role="assistant",
        parts=[
            MessagePart.from_function_call(
                FunctionCall(name=func_name, arguments={"arg": "value"})
            )
        ],
    )


def create_function_response_message(func_name: str, result: str) -> Message:
    """Create a tool message with function response."""
    return Message(
        role="tool",
        parts=[
            MessagePart.from_function_response(
                FunctionResponse(name=func_name, response={"result": result})
            )
        ],
    )


class TestFunctionCallPairing:
    """Test function call/response pairing in history management."""

    def test_is_function_call_pair_valid(self):
        """Test detection of valid function call/response pairs."""
        manager = HistoryManager(max_messages=50, max_tokens=100000)

        # Add a valid pair
        manager.add_message(create_function_call_message("test_func"), allow_incomplete=True)
        manager.add_message(create_function_response_message("test_func", "success"))

        # Check if pair is detected
        assert manager._is_function_call_pair(0) is True

    def test_is_function_call_pair_invalid(self):
        """Test detection of non-pairs."""
        manager = HistoryManager(max_messages=50, max_tokens=100000)

        # Add two regular messages
        manager.add_message(create_user_message("Hello"))
        manager.add_message(create_model_message("Hi there"))

        # Should not be detected as a pair
        assert manager._is_function_call_pair(0) is False

    def test_is_function_call_pair_orphaned_call(self):
        """Test detection when function call is not followed by response."""
        manager = HistoryManager(max_messages=50, max_tokens=100000)

        # Add function call followed by regular message
        manager.add_message(create_function_call_message("test_func"), allow_incomplete=True)
        manager.add_message(create_model_message("Some text"))

        # Should not be detected as a pair
        assert manager._is_function_call_pair(0) is False

    def test_is_function_call_pair_orphaned_response(self):
        """Test detection when function response is not preceded by call."""
        manager = HistoryManager(max_messages=50, max_tokens=100000)

        # Add regular message followed by function response
        manager.add_message(create_model_message("Some text"))
        manager.add_message(create_function_response_message("test_func", "success"))

        # Should not be detected as a pair
        assert manager._is_function_call_pair(0) is False

    def test_prune_preserves_pairs(self):
        """Test that pruning preserves function call/response pairs."""
        manager = HistoryManager(max_messages=6, max_tokens=100000)

        # Add messages: user, assistant, fc, fr, user, assistant, user
        manager.add_message(create_user_message("msg1"))
        manager.add_message(create_model_message("msg2"))
        manager.add_message(create_function_call_message("func1"), allow_incomplete=True)
        manager.add_message(create_function_response_message("func1", "result1"))
        manager.add_message(create_user_message("msg3"))
        manager.add_message(create_model_message("msg4"))
        manager.add_message(create_user_message("msg5"))  # This triggers pruning

        history = manager.get_history()

        # Should have 6 messages (max_messages limit)
        assert len(history) <= 6

        # Verify no orphaned function responses at the start
        if history and history[0].role == "tool":
            assert not any(part.function_response for part in history[0].parts)

        # Verify no orphaned function calls at the end
        if history and history[-1].role == "assistant":
            assert not any(part.function_call for part in history[-1].parts)

    def test_prune_removes_pairs_together(self):
        """Test that pruning removes function call/response pairs together."""
        manager = HistoryManager(max_messages=4, max_tokens=100000)

        # Add a pair followed by regular messages
        manager.add_message(create_function_call_message("func1"), allow_incomplete=True)
        manager.add_message(create_function_response_message("func1", "result1"))
        manager.add_message(create_user_message("msg1"))
        manager.add_message(create_model_message("msg2"))
        manager.add_message(create_user_message("msg3"))  # Triggers pruning

        history = manager.get_history()

        # Should have removed the pair together, not just one part
        # History should be: msg1, msg2, msg3
        assert len(history) <= 4

        # First message should not be an orphaned function response
        if history:
            first = history[0]
            if first.role == "tool":
                assert not any(part.function_response for part in first.parts)

    def test_fix_broken_pairs_removes_orphaned_response(self):
        """Test that _fix_broken_pairs removes orphaned function responses."""
        manager = HistoryManager(max_messages=50, max_tokens=100000)

        # Manually create a broken history (orphaned response at start)
        manager._history = [
            create_function_response_message("func1", "result1"),
            create_user_message("msg1"),
            create_model_message("msg2"),
        ]

        manager._fix_broken_pairs()

        # Orphaned response should be removed
        history = manager.get_history()
        assert len(history) == 2
        assert history[0].role == "user"
        assert not any(part.function_response for part in history[0].parts)

    def test_fix_broken_pairs_removes_orphaned_call(self):
        """Test that _fix_broken_pairs removes orphaned function calls."""
        manager = HistoryManager(max_messages=50, max_tokens=100000)

        # Manually create a broken history (orphaned call at end)
        manager._history = [
            create_user_message("msg1"),
            create_model_message("msg2"),
            create_function_call_message("func1"),
        ]

        manager._fix_broken_pairs()

        # Orphaned call should be removed
        history = manager.get_history()
        assert len(history) == 2
        assert history[-1].role == "assistant"
        assert not any(part.function_call for part in history[-1].parts)

    def test_token_based_pruning_respects_pairs(self):
        """Test that token-based pruning respects function call/response pairs."""
        # Use very low token limit to force pruning
        manager = HistoryManager(max_messages=50, max_tokens=100)

        # Add a pair (will exceed token limit)
        manager.add_message(create_function_call_message("func1"), allow_incomplete=True)
        manager.add_message(create_function_response_message("func1", "result1"))
        manager.add_message(create_user_message("This is a long message that will exceed the token limit"))

        history = manager.get_history()

        # If the pair was removed, both should be gone
        if len(history) < 3:
            assert not any(
                msg.role == "assistant" and any(part.function_call for part in msg.parts)
                for msg in history
            )
            assert not any(
                msg.role == "tool" and any(part.function_response for part in msg.parts)
                for msg in history
            )
