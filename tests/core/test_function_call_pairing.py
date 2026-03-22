"""Tests for function call/response pairing in HistoryManager."""

from resume_agent.core.llm import HistoryManager
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
        parts=[MessagePart.from_function_call(FunctionCall(name=func_name, arguments={"arg": "value"}))],
    )


def create_function_response_message(func_name: str, result: str) -> Message:
    """Create a tool message with function response."""
    return Message(
        role="tool",
        parts=[MessagePart.from_function_response(FunctionResponse(name=func_name, response={"result": result}))],
    )


class TestFunctionCallPairing:
    """Test function call/response pairing in history management."""

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
            assert not any(msg.role == "assistant" and any(part.function_call for part in msg.parts) for msg in history)
            assert not any(msg.role == "tool" and any(part.function_response for part in msg.parts) for msg in history)
