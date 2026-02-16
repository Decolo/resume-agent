"""Session persistence - Save/load conversation sessions."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from packages.providers.resume_agent_providers.types import (
    FunctionCall,
    FunctionResponse,
    Message,
    MessagePart,
)

from .llm import HistoryManager
from .observability import AgentEvent, AgentObserver


class SessionSerializer:
    """Serialize/deserialize agent state to/from JSON."""

    @staticmethod
    def serialize_message(msg: Message) -> dict:
        """Convert Message to JSON dict.

        Pattern from cli.py /export command (lines 266-287).
        """
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
                    # Serialize function response - store the actual response dict
                    response_value = part.function_response.response
                    if not isinstance(response_value, dict):
                        # If it's not a dict, convert to string and wrap
                        response_value = str(response_value)

                    msg_data["parts"].append(
                        {
                            "type": "function_response",
                            "name": part.function_response.name,
                            "response": response_value,
                            "call_id": part.function_response.call_id,
                        }
                    )

        return msg_data

    @staticmethod
    def deserialize_message(data: dict) -> Message:
        """Reconstruct Message from JSON dict."""
        parts: List[MessagePart] = []

        for part_data in data.get("parts", []):
            if part_data["type"] == "text":
                parts.append(MessagePart.from_text(text=part_data["content"]))
            elif part_data["type"] == "function_call":
                parts.append(
                    MessagePart.from_function_call(
                        FunctionCall(
                            name=part_data["name"],
                            arguments=part_data.get("args", {}) or {},
                            id=part_data.get("id"),
                        )
                    )
                )
            elif part_data["type"] == "function_response":
                # Function response expects a dict, not a string
                response_data = part_data["response"]
                if isinstance(response_data, str):
                    # If it's a string, wrap it in a dict
                    response_data = {"result": response_data}
                parts.append(
                    MessagePart.from_function_response(
                        FunctionResponse(
                            name=part_data["name"],
                            response=response_data,
                            call_id=part_data.get("call_id"),
                        )
                    )
                )

        role = data.get("role", "user")
        if role == "model":
            role = "assistant"
        if role == "user" and any(part.function_response for part in parts):
            role = "tool"

        return Message(role=role, parts=parts)

    @staticmethod
    def serialize_history(history_manager: HistoryManager) -> dict:
        """Serialize conversation history."""
        return {
            "messages": [SessionSerializer.serialize_message(msg) for msg in history_manager.get_history()],
            "max_messages": history_manager.max_messages,
            "max_tokens": history_manager.max_tokens,
        }

    @staticmethod
    def deserialize_history(data: dict) -> List[Message]:
        """Deserialize conversation history."""
        return [SessionSerializer.deserialize_message(msg_data) for msg_data in data.get("messages", [])]

    @staticmethod
    def serialize_observability(observer: AgentObserver) -> dict:
        """Serialize observability events and stats."""
        events_data = []
        for event in observer.events:
            event_data = {
                "timestamp": event.timestamp.isoformat(),
                "event_type": event.event_type,
                "data": event.data,
                "duration_ms": event.duration_ms,
                "tokens_used": event.tokens_used,
                "cost_usd": event.cost_usd,
            }
            events_data.append(event_data)

        return {
            "events": events_data,
            "session_stats": observer.get_session_stats(),
        }

    @staticmethod
    def deserialize_observability(data: dict) -> List[AgentEvent]:
        """Deserialize observability events."""
        events = []
        for event_data in data.get("events", []):
            event = AgentEvent(
                timestamp=datetime.fromisoformat(event_data["timestamp"]),
                event_type=event_data["event_type"],
                data=event_data["data"],
                duration_ms=event_data.get("duration_ms"),
                tokens_used=event_data.get("tokens_used"),
                cost_usd=event_data.get("cost_usd"),
            )
            events.append(event)
        return events

    @staticmethod
    def serialize_multi_agent_state(agent) -> dict:
        """Serialize multi-agent specific state.

        Args:
            agent: OrchestratorAgent instance

        Returns:
            Dictionary with delegation history, agent stats, shared context
        """
        from resume_agent.agents.orchestrator_agent import OrchestratorAgent

        if not isinstance(agent, OrchestratorAgent):
            return {}

        # Serialize delegation history
        delegation_history = []
        if agent.delegation_manager:
            for record in agent.delegation_manager._delegation_history:
                delegation_history.append(
                    {
                        "task_id": record.task_id,
                        "from_agent": record.from_agent,
                        "to_agent": record.to_agent,
                        "timestamp": record.timestamp.isoformat(),
                        "duration_ms": record.duration_ms,
                        "success": record.success,
                    }
                )

        # Serialize agent stats
        agent_stats = agent.get_agent_stats() if hasattr(agent, "get_agent_stats") else {}

        return {
            "delegation_history": delegation_history,
            "agent_stats": agent_stats,
        }


class SessionIndex:
    """Fast session lookup and metadata management."""

    def __init__(self, index_path: Path):
        self.index_path = index_path
        self.index = self._load_index()

    def add_session(self, session_id: str, metadata: dict):
        """Add session to index."""
        self.index["sessions"][session_id] = metadata
        self._save_index()

    def remove_session(self, session_id: str):
        """Remove session from index."""
        if session_id in self.index["sessions"]:
            del self.index["sessions"][session_id]
            self._save_index()

    def get_session_metadata(self, session_id: str) -> Optional[dict]:
        """Get session metadata without loading full file."""
        return self.index["sessions"].get(session_id)

    def list_all(self) -> List[dict]:
        """List all sessions sorted by updated_at."""
        sessions = []
        for session_id, metadata in self.index["sessions"].items():
            sessions.append({"id": session_id, **metadata})

        # Sort by updated_at (most recent first)
        sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return sessions

    def _load_index(self) -> dict:
        """Load index from disk."""
        if self.index_path.exists():
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                # If index is corrupted, start fresh
                return {"sessions": {}}
        return {"sessions": {}}

    def _save_index(self):
        """Save index to disk."""
        try:
            with open(self.index_path, "w", encoding="utf-8") as f:
                json.dump(self.index, f, indent=2)
        except Exception as e:
            # Log error but don't crash
            print(f"Warning: Failed to save session index: {e}")


class SessionManager:
    """Manage session lifecycle: save, load, list, delete."""

    def __init__(self, workspace_dir: str):
        self.workspace_dir = Path(workspace_dir)
        self.sessions_dir = self.workspace_dir / "sessions"
        self.sessions_dir.mkdir(exist_ok=True)
        self.index = SessionIndex(self.sessions_dir / ".index.json")

    def save_session(
        self,
        agent: Any,
        session_id: Optional[str] = None,
        session_name: Optional[str] = None,
    ) -> str:
        """Save current session to JSON file.

        Args:
            agent: ResumeAgent, OrchestratorAgent, or AutoAgent instance
            session_id: Optional session ID to update existing session
            session_name: Optional custom name for the session

        Returns:
            Session ID
        """
        from resume_agent.agents.orchestrator_agent import OrchestratorAgent

        from .agent_factory import AutoAgent

        # Generate or reuse session ID
        if session_id is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            if session_name:
                session_id = f"session_{timestamp}_{session_name}_{unique_id}"
            else:
                session_id = f"session_{timestamp}_{unique_id}"

        # Determine agent mode and get LLM agent
        if isinstance(agent, AutoAgent):
            # AutoAgent: use single-agent for session management
            is_multi_agent = False
            mode = "auto-agent"
            llm_agent = agent.agent
        elif isinstance(agent, OrchestratorAgent):
            is_multi_agent = True
            mode = "multi-agent"
            llm_agent = agent.llm_agent
        else:
            # ResumeAgent
            is_multi_agent = False
            mode = "single-agent"
            llm_agent = agent.agent

        # Get config
        if isinstance(agent, AutoAgent):
            # AutoAgent: use single-agent config
            config_data = {
                "model": agent.single_agent.llm_config.model,
                "max_tokens": agent.single_agent.llm_config.max_tokens,
                "temperature": agent.single_agent.llm_config.temperature,
                "workspace_dir": agent.single_agent.agent_config.workspace_dir,
            }
        elif is_multi_agent:
            config_data = {
                "model": agent.config.model,
                "max_tokens": agent.config.max_tokens,
                "temperature": agent.config.temperature,
            }
        else:
            config_data = {
                "model": agent.llm_config.model,
                "max_tokens": agent.llm_config.max_tokens,
                "temperature": agent.llm_config.temperature,
                "workspace_dir": agent.agent_config.workspace_dir,
            }

        # Serialize conversation history
        conversation_data = SessionSerializer.serialize_history(llm_agent.history_manager)

        # Serialize observability data
        observability_data = SessionSerializer.serialize_observability(llm_agent.observer)

        # Serialize multi-agent state (if applicable)
        multi_agent_data = {}
        if is_multi_agent:
            multi_agent_data = SessionSerializer.serialize_multi_agent_state(agent)

        # Build session data
        now = datetime.now()
        session_data = {
            "schema_version": "1.0",
            "session": {
                "id": session_id,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "mode": mode,
                "workspace_dir": str(self.workspace_dir),
                "config": config_data,
            },
            "conversation": conversation_data,
            "observability": observability_data,
        }

        if multi_agent_data:
            session_data["multi_agent"] = multi_agent_data

        # Save to file
        session_file = self.sessions_dir / f"{session_id}.json"
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2)

        # Update index
        message_count = len(conversation_data["messages"])
        stats = observability_data.get("session_stats", {})
        self.index.add_session(
            session_id,
            {
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "mode": mode,
                "message_count": message_count,
                "total_tokens": stats.get("total_tokens", 0),
                "total_cost_usd": stats.get("total_cost_usd", 0.0),
            },
        )

        return session_id

    def load_session(self, session_id: str) -> dict:
        """Load session from JSON file.

        Args:
            session_id: Session ID to load

        Returns:
            Session data dictionary

        Raises:
            FileNotFoundError: If session file doesn't exist
        """
        session_file = self.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")

        with open(session_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_sessions(self) -> List[dict]:
        """List all sessions with metadata.

        Returns:
            List of session metadata dictionaries
        """
        return self.index.list_all()

    def delete_session(self, session_id: str) -> bool:
        """Delete a session file.

        Args:
            session_id: Session ID to delete

        Returns:
            True if deleted, False if not found
        """
        session_file = self.sessions_dir / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()
            self.index.remove_session(session_id)
            return True
        return False

    def get_latest_session(self) -> Optional[str]:
        """Get most recent session ID.

        Returns:
            Session ID or None if no sessions exist
        """
        sessions = self.list_sessions()
        if sessions:
            return sessions[0]["id"]
        return None

    def restore_agent_state(self, agent: Any, session_data: dict):
        """Restore agent state from session data.

        Args:
            agent: ResumeAgent, OrchestratorAgent, or AutoAgent instance
            session_data: Session data dictionary from load_session()
        """
        from resume_agent.agents.delegation import DelegationRecord
        from resume_agent.agents.orchestrator_agent import OrchestratorAgent

        from .agent_factory import AutoAgent

        # Handle AutoAgent
        if isinstance(agent, AutoAgent):
            # Restore to single-agent (AutoAgent uses single-agent for history)
            actual_agent = agent.single_agent
            is_multi_agent = False
        elif isinstance(agent, OrchestratorAgent):
            actual_agent = agent
            is_multi_agent = True
        else:
            actual_agent = agent
            is_multi_agent = False

        # Get LLM agent
        if isinstance(agent, AutoAgent):
            llm_agent = agent.agent
        elif is_multi_agent:
            llm_agent = actual_agent.llm_agent
        else:
            llm_agent = actual_agent.agent

        # 1. Restore conversation history
        messages = SessionSerializer.deserialize_history(session_data["conversation"])
        llm_agent.history_manager._history = messages

        # 2. Restore observability events
        events = SessionSerializer.deserialize_observability(session_data["observability"])
        llm_agent.observer.events = events

        # 3. Restore multi-agent state (if applicable)
        if is_multi_agent and "multi_agent" in session_data:
            ma_data = session_data["multi_agent"]

            # Restore delegation history
            if actual_agent.delegation_manager and "delegation_history" in ma_data:
                actual_agent.delegation_manager._delegation_history = []
                for record_data in ma_data["delegation_history"]:
                    record = DelegationRecord(
                        task_id=record_data["task_id"],
                        from_agent=record_data["from_agent"],
                        to_agent=record_data["to_agent"],
                        timestamp=datetime.fromisoformat(record_data["timestamp"]),
                        duration_ms=record_data.get("duration_ms"),
                        success=record_data.get("success"),
                    )
                    actual_agent.delegation_manager._delegation_history.append(record)
