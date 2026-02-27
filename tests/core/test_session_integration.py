"""Integration test for session persistence with agent."""

import pytest

from resume_agent.core.agent import AgentConfig, ResumeAgent
from resume_agent.core.llm import LLMConfig
from resume_agent.core.session import SessionManager
from resume_agent.providers.types import Message, MessagePart


@pytest.mark.asyncio
async def test_session_save_load_integration(tmp_path):
    """Test full session save/load workflow with ResumeAgent."""
    # Create agent with session manager
    config = LLMConfig(api_key="test_key", model="gemini-2.5-flash")
    agent_config = AgentConfig(workspace_dir=str(tmp_path))
    session_manager = SessionManager(str(tmp_path))

    agent = ResumeAgent(llm_config=config, agent_config=agent_config, session_manager=session_manager)

    # Simulate conversation by adding messages directly
    agent.agent.history_manager.add_message(Message(role="user", parts=[MessagePart.from_text("Hello")]))
    agent.agent.history_manager.add_message(Message(role="assistant", parts=[MessagePart.from_text("Hi there!")]))

    # Save session
    session_id = session_manager.save_session(agent, session_name="test_session")
    assert session_id is not None
    assert "test_session" in session_id

    # Verify session file exists
    session_file = tmp_path / "sessions" / f"{session_id}.json"
    assert session_file.exists()

    # Create new agent and load session
    new_agent = ResumeAgent(llm_config=config, agent_config=agent_config, session_manager=session_manager)

    # Load session
    session_data = session_manager.load_session(session_id)
    session_manager.restore_agent_state(new_agent, session_data)

    # Verify history was restored
    restored_history = new_agent.agent.history_manager.get_history()
    assert len(restored_history) == 2
    assert restored_history[0].role == "user"
    assert restored_history[1].role == "assistant"


@pytest.mark.asyncio
async def test_session_list_and_delete(tmp_path):
    """Test listing and deleting sessions."""
    config = LLMConfig(api_key="test_key", model="gemini-2.5-flash")
    agent_config = AgentConfig(workspace_dir=str(tmp_path))
    session_manager = SessionManager(str(tmp_path))

    agent = ResumeAgent(llm_config=config, agent_config=agent_config, session_manager=session_manager)

    # Create multiple sessions
    session_ids = []
    for i in range(3):
        agent.agent.history_manager.add_message(Message(role="user", parts=[MessagePart.from_text(f"Message {i}")]))
        session_id = session_manager.save_session(agent, session_name=f"session_{i}")
        session_ids.append(session_id)

    # List sessions
    sessions = session_manager.list_sessions()
    assert len(sessions) == 3

    # Delete one session
    result = session_manager.delete_session(session_ids[0])
    assert result is True

    # Verify it's gone
    sessions = session_manager.list_sessions()
    assert len(sessions) == 2
    assert session_ids[0] not in [s["id"] for s in sessions]
