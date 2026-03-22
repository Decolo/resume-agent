"""Black-box behavior tests for history compaction."""

from __future__ import annotations

import pytest

from resume_agent.core.llm import (
    CompactionSummary,
    HistoryManager,
    LLMAgent,
    LLMConfig,
)
from resume_agent.core.session import SessionManager
from resume_agent.providers.types import FunctionCall, FunctionResponse, Message, MessagePart


def _assistant_text(text: str) -> Message:
    return Message(role="assistant", parts=[MessagePart.from_text(text)])


def _assistant_tool_call(name: str, **arguments: str) -> Message:
    return Message(
        role="assistant",
        parts=[MessagePart.from_function_call(FunctionCall(name=name, arguments=arguments))],
    )


def _tool_response(name: str, result: str) -> Message:
    return Message(
        role="tool",
        parts=[MessagePart.from_function_response(FunctionResponse(name=name, response={"result": result}))],
    )


class _RecordingSummarizer:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def __call__(self, messages, prior_state):  # noqa: ANN001
        rendered = []
        for msg in messages:
            text_parts = [part.text for part in msg.parts if part.text]
            if text_parts:
                rendered.append(" ".join(text_parts))
                continue
            if any(part.function_call for part in msg.parts):
                rendered.append(f"tool-call:{msg.parts[0].function_call.name}")
                continue
            if any(part.function_response for part in msg.parts):
                rendered.append(f"tool-result:{msg.parts[0].function_response.name}")
        self.calls.append(rendered)
        return CompactionSummary(summary_text=" | ".join(rendered))


class _MockResumeAgent:
    def __init__(self, llm_agent: LLMAgent, workspace_dir: str) -> None:
        self.agent = llm_agent
        self.llm_config = llm_agent.config
        self.agent_config = type("AgentConfig", (), {"workspace_dir": workspace_dir})()


@pytest.mark.asyncio
async def test_compact_summarizes_older_turns_while_preserving_a_complete_recent_tool_tail():
    manager = HistoryManager(max_messages=50, max_tokens=10_000)
    summarizer = _RecordingSummarizer()

    manager.add_message(Message.user("Need help tailoring this resume for a backend role."))
    manager.add_message(_assistant_tool_call("file_read", path="resume.md"), allow_incomplete=True)
    manager.add_message(_tool_response("file_read", "Loaded resume.md"))
    manager.add_message(_assistant_text("I found a few bullets that can be tightened."))
    manager.add_message(Message.user("Rewrite the experience bullet to emphasize Python ownership."))
    manager.add_message(
        _assistant_tool_call("file_write", path="resume.md", content="new bullet"), allow_incomplete=True
    )
    manager.add_message(_tool_response("file_write", "Updated resume.md"))
    manager.add_message(_assistant_text("I updated the bullet and kept the rest unchanged."))

    compacted = await manager.compact(summarizer=summarizer, tail_tokens=25)

    assert compacted is True
    assert len(summarizer.calls) == 1
    assert summarizer.calls[0] == [
        "Need help tailoring this resume for a backend role.",
        "tool-call:file_read",
        "tool-result:file_read",
        "I found a few bullets that can be tightened.",
    ]

    history = manager.get_active_history()

    assert len(history) == 5
    assert history[0].role == "assistant"
    assert history[0].parts[0].text.startswith("[COMPRESSION_STATE]")
    assert history[1].parts[0].text == "Rewrite the experience bullet to emphasize Python ownership."
    assert history[2].parts[0].function_call.name == "file_write"
    assert history[3].parts[0].function_response.name == "file_write"
    assert history[4].parts[0].text == "I updated the bullet and kept the rest unchanged."


@pytest.mark.asyncio
async def test_resume_restores_compacted_history_instead_of_the_full_pre_compaction_transcript(tmp_path):
    manager = HistoryManager(max_messages=50, max_tokens=10_000)
    summarizer = _RecordingSummarizer()

    manager.add_message(Message.user("Need help tailoring this resume for a backend role."))
    manager.add_message(_assistant_tool_call("file_read", path="resume.md"), allow_incomplete=True)
    manager.add_message(_tool_response("file_read", "Loaded resume.md"))
    manager.add_message(_assistant_text("I found a few bullets that can be tightened."))
    manager.add_message(Message.user("Rewrite the experience bullet to emphasize Python ownership."))
    manager.add_message(
        _assistant_tool_call("file_write", path="resume.md", content="new bullet"), allow_incomplete=True
    )
    manager.add_message(_tool_response("file_write", "Updated resume.md"))
    manager.add_message(_assistant_text("I updated the bullet and kept the rest unchanged."))
    await manager.compact(summarizer=summarizer, tail_tokens=25)

    config = LLMConfig(api_key="test_key", model="gemini-2.5-flash")
    llm_agent = LLMAgent(config=config, system_prompt="Test prompt")
    llm_agent.history_manager = manager
    agent = _MockResumeAgent(llm_agent, str(tmp_path))
    session_manager = SessionManager(str(tmp_path))

    session_id = session_manager.save_session(agent)
    session_data = session_manager.load_session(session_id)

    restored_llm_agent = LLMAgent(config=config, system_prompt="Test prompt")
    restored_agent = _MockResumeAgent(restored_llm_agent, str(tmp_path))
    session_manager.restore_agent_state(restored_agent, session_data)

    restored_history = restored_llm_agent.history_manager.get_active_history()

    assert len(restored_history) == 5
    assert restored_history[0].parts[0].text.startswith("[COMPRESSION_STATE]")
    assert restored_history[1].parts[0].text == "Rewrite the experience bullet to emphasize Python ownership."
    assert restored_history[2].parts[0].function_call.name == "file_write"
    assert restored_history[3].parts[0].function_response.name == "file_write"
    assert restored_llm_agent.history_manager.get_compression_state() is not None
    assert len(restored_llm_agent.history_manager.get_compaction_checkpoints()) == 1


@pytest.mark.asyncio
async def test_second_compact_summarizes_only_turns_added_since_the_previous_checkpoint():
    manager = HistoryManager(max_messages=50, max_tokens=10_000)
    summarizer = _RecordingSummarizer()

    manager.add_message(Message.user("Need help tailoring this resume for a backend role."))
    manager.add_message(_assistant_tool_call("file_read", path="resume.md"), allow_incomplete=True)
    manager.add_message(_tool_response("file_read", "Loaded resume.md"))
    manager.add_message(_assistant_text("I found a few bullets that can be tightened."))
    manager.add_message(Message.user("Rewrite the experience bullet to emphasize Python ownership."))
    manager.add_message(
        _assistant_tool_call("file_write", path="resume.md", content="new bullet"), allow_incomplete=True
    )
    manager.add_message(_tool_response("file_write", "Updated resume.md"))
    manager.add_message(_assistant_text("I updated the bullet and kept the rest unchanged."))
    await manager.compact(summarizer=summarizer, tail_tokens=25)

    manager.add_message(Message.user("Now also highlight mentoring and code review leadership."))
    manager.add_message(
        _assistant_tool_call("file_write", path="resume.md", content="mentoring bullet"),
        allow_incomplete=True,
    )
    manager.add_message(_tool_response("file_write", "Updated mentoring bullet"))
    manager.add_message(_assistant_text("I added mentoring and code review ownership."))

    compacted = await manager.compact(summarizer=summarizer, tail_tokens=25)

    assert compacted is True
    assert len(summarizer.calls) == 2
    assert summarizer.calls[1] == [
        "Rewrite the experience bullet to emphasize Python ownership.",
        "tool-call:file_write",
        "tool-result:file_write",
        "I updated the bullet and kept the rest unchanged.",
    ]

    state = manager.get_compression_state()
    assert state is not None
    assert state.covered_messages == 8
    assert len(state.summary_chunks) == 2
    assert len(manager.get_compaction_checkpoints()) == 2

    history = manager.get_active_history()
    assert history[0].parts[0].text.startswith("[COMPRESSION_STATE]")
    assert history[1].parts[0].text == "Now also highlight mentoring and code review leadership."
    assert history[2].parts[0].function_call.name == "file_write"
    assert history[3].parts[0].function_response.name == "file_write"
    assert history[4].parts[0].text == "I added mentoring and code review ownership."
