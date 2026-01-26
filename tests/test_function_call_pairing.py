"""Tests for function call/response pairing in HistoryManager."""

import pytest
from google.genai import types
from resume_agent.llm import HistoryManager


def create_user_message(text: str) -> types.Content:
    """Create a user message."""
    return types.Content(
        role="user",
        parts=[types.Part.from_text(text=text)],
    )


def create_model_message(text: str) -> types.Content:
    """Create a model message."""
    return types.Content(
        role="model",
        parts=[types.Part.from_text(text=text)],
    )


def create_function_call_message(func_name: str) -> types.Content:
    """Create a model message with function call."""
    return types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(
                    name=func_name,
                    args={"arg": "value"}
                )
            )
        ],
    )


def create_function_response_message(func_name: str, result: str) -> types.Content:
    """Create a user message with function response."""
    return types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    name=func_name,
                    response={"result": result}
                )
            )
        ],
    )


class TestFunctionCallPairing:
    """Test function call/response pairing in history management."""

    def test_is_function_call_pair_valid(self):
        """Test detection of valid function call/response pairs."""
        manager = HistoryManager(max_messages=50, max_tokens=100000)

        # Add a valid pair
        manager.add_message(create_function_call_message("test_func"))
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
        manager.add_message(create_function_call_message("test_func"))
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

        # Add messages: user, model, fc, fr, user, model, user
        manager.add_message(create_user_message("msg1"))
        manager.add_message(create_model_message("msg2"))
        manager.add_message(create_function_call_message("func1"))
        manager.add_message(create_function_response_message("func1", "result1"))
        manager.add_message(create_user_message("msg3"))
        manager.add_message(create_model_message("msg4"))
        manager.add_message(create_user_message("msg5"))  # This triggers pruning

        history = manager.get_history()

        # Should have 6 messages (max_messages limit)
        assert len(history) <= 6

        # Verify no orphaned function responses at the start
        if history and history[0].role == "user":
            assert not any(part.function_response for part in history[0].parts)

        # Verify no orphaned function calls at the end
        if history and history[-1].role == "model":
            assert not any(part.function_call for part in history[-1].parts)

    def test_prune_removes_pairs_together(self):
        """Test that pruning removes function call/response pairs together."""
        manager = HistoryManager(max_messages=4, max_tokens=100000)

        # Add a pair followed by regular messages
        manager.add_message(create_function_call_message("func1"))
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
            if first.role == "user":
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
        assert history[-1].role == "model"
        assert not any(part.function_call for part in history[-1].parts)

    def test_token_based_pruning_respects_pairs(self):
        """Test that token-based pruning respects function call/response pairs."""
        # Use very low token limit to force pruning
        manager = HistoryManager(max_messages=50, max_tokens=100)

        # Add a pair (will exceed token limit)
        manager.add_message(create_function_call_message("func1"))
        manager.add_message(create_function_response_message("func1", "result1"))
        manager.add_message(create_user_message("This is a long message that will exceed the token limit"))

        history = manager.get_history()

        # If the pair was removed, both should be gone
        has_call = any(
            any(part.function_call for part in msg.parts)
            for msg in history
        )
        has_response = any(
            any(part.function_response for part in msg.parts)
            for msg in history
        )

        # Either both present or both absent
        assert has_call == has_response

    def test_multiple_pairs_pruning(self):
        """Test pruning with multiple function call/response pairs."""
        manager = HistoryManager(max_messages=8, max_tokens=100000)

        # Add multiple pairs
        manager.add_message(create_function_call_message("func1"))
        manager.add_message(create_function_response_message("func1", "result1"))
        manager.add_message(create_function_call_message("func2"))
        manager.add_message(create_function_response_message("func2", "result2"))
        manager.add_message(create_user_message("msg1"))
        manager.add_message(create_model_message("msg2"))
        manager.add_message(create_function_call_message("func3"))
        manager.add_message(create_function_response_message("func3", "result3"))
        manager.add_message(create_user_message("msg3"))  # Triggers pruning

        history = manager.get_history()

        # Verify no orphaned calls or responses
        for i, msg in enumerate(history):
            if msg.role == "model" and any(part.function_call for part in msg.parts):
                # Next message should be function response
                if i + 1 < len(history):
                    next_msg = history[i + 1]
                    assert next_msg.role == "user"
                    assert any(part.function_response for part in next_msg.parts)

            if msg.role == "user" and any(part.function_response for part in msg.parts):
                # Previous message should be function call
                if i > 0:
                    prev_msg = history[i - 1]
                    assert prev_msg.role == "model"
                    assert any(part.function_call for part in prev_msg.parts)

    def test_empty_history_fix_broken_pairs(self):
        """Test _fix_broken_pairs with empty history."""
        manager = HistoryManager(max_messages=50, max_tokens=100000)

        # Should not raise error on empty history
        manager._fix_broken_pairs()
        assert len(manager.get_history()) == 0

    def test_single_message_fix_broken_pairs(self):
        """Test _fix_broken_pairs with single message."""
        manager = HistoryManager(max_messages=50, max_tokens=100000)

        manager.add_message(create_user_message("msg1"))
        manager._fix_broken_pairs()

        # Single regular message should remain
        assert len(manager.get_history()) == 1
