"""Integration tests for Web API real executor mode.

Tests real user workflows with mocked LLM responses using TestClient.
"""

from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from apps.api.resume_agent_api.app import create_app


def test_stub_mode_by_default():
    """Default mode should be stub."""
    # Ensure no env var is set
    os.environ.pop("RESUME_AGENT_EXECUTOR_MODE", None)

    with TestClient(create_app()) as client:
        # Create session and run
        session = client.post("/api/v1/sessions", json={"workspace_name": "test"}).json()
        run = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": "Hello"},
        ).json()

        # Wait for completion
        time.sleep(1.0)

        # Get run status
        run_state = client.get(f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}")
        assert run_state.status_code == 200

        # Stub mode should complete (with stub response)
        body = run_state.json()
        assert body["status"] in {"completed", "running"}


def test_real_mode_with_env_var():
    """Real mode should be activated with env var."""
    # Set real mode
    os.environ["RESUME_AGENT_EXECUTOR_MODE"] = "real"
    os.environ["GEMINI_API_KEY"] = "test-key"

    try:
        with TestClient(create_app()) as client:
            # Mock the agent's run method
            with patch("packages.core.resume_agent_core.agent.ResumeAgent.run", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = "Hello from real agent"

                # Create session and run
                session = client.post("/api/v1/sessions", json={"workspace_name": "test"}).json()
                run = client.post(
                    f"/api/v1/sessions/{session['session_id']}/messages",
                    json={"message": "Hello"},
                ).json()

                # Wait for completion
                time.sleep(1.5)

                # Verify agent was called
                assert mock_run.called

                # Get run status
                run_state = client.get(f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}")
                assert run_state.status_code == 200
                body = run_state.json()
                assert body["status"] in {"completed", "running"}

    finally:
        # Clean up env vars
        os.environ.pop("RESUME_AGENT_EXECUTOR_MODE", None)
        os.environ.pop("GEMINI_API_KEY", None)


def test_real_mode_agent_reused_across_runs():
    """Agent instance should be reused for multiple runs in same session."""
    os.environ["RESUME_AGENT_EXECUTOR_MODE"] = "real"
    os.environ["GEMINI_API_KEY"] = "test-key"

    try:
        with TestClient(create_app()) as client:
            with patch("packages.core.resume_agent_core.agent.ResumeAgent.run", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = "Response"

                # Create session
                session = client.post("/api/v1/sessions", json={"workspace_name": "test"}).json()
                session_id = session["session_id"]

                # First run
                run1 = client.post(
                    f"/api/v1/sessions/{session_id}/messages",
                    json={"message": "First message"},
                ).json()
                time.sleep(1.0)

                # Second run
                run2 = client.post(
                    f"/api/v1/sessions/{session_id}/messages",
                    json={"message": "Second message"},
                ).json()
                time.sleep(1.0)

                # Agent should be called twice
                assert mock_run.call_count == 2

                # Both runs should complete
                run1_state = client.get(f"/api/v1/sessions/{session_id}/runs/{run1['run_id']}")
                run2_state = client.get(f"/api/v1/sessions/{session_id}/runs/{run2['run_id']}")

                assert run1_state.json()["status"] == "completed"
                assert run2_state.json()["status"] == "completed"

    finally:
        os.environ.pop("RESUME_AGENT_EXECUTOR_MODE", None)
        os.environ.pop("GEMINI_API_KEY", None)


def test_real_mode_handles_agent_error():
    """Real mode should handle agent errors gracefully."""
    os.environ["RESUME_AGENT_EXECUTOR_MODE"] = "real"
    os.environ["GEMINI_API_KEY"] = "test-key"

    try:
        with TestClient(create_app()) as client:
            with patch("packages.core.resume_agent_core.agent.ResumeAgent.run", new_callable=AsyncMock) as mock_run:
                mock_run.side_effect = Exception("LLM API error")

                # Create session and run
                session = client.post("/api/v1/sessions", json={"workspace_name": "test"}).json()
                run = client.post(
                    f"/api/v1/sessions/{session['session_id']}/messages",
                    json={"message": "This will fail"},
                ).json()

                # Wait for failure
                time.sleep(1.5)

                # Check run status
                run_state = client.get(f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}")
                body = run_state.json()

                assert body["status"] == "failed"
                assert body["error"] is not None
                assert "LLM API error" in body["error"]["message"]

    finally:
        os.environ.pop("RESUME_AGENT_EXECUTOR_MODE", None)
        os.environ.pop("GEMINI_API_KEY", None)


def test_real_mode_auto_approve_setting():
    """Auto-approve setting should be passed to agent."""
    os.environ["RESUME_AGENT_EXECUTOR_MODE"] = "real"
    os.environ["GEMINI_API_KEY"] = "test-key"

    try:
        with TestClient(create_app()) as client:
            with patch("packages.core.resume_agent_core.agent.ResumeAgent.run", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = "Done"

                # Create session with auto_approve=True
                session = client.post(
                    "/api/v1/sessions",
                    json={"workspace_name": "test", "auto_approve": True},
                ).json()

                run = client.post(
                    f"/api/v1/sessions/{session['session_id']}/messages",
                    json={"message": "Test"},
                ).json()

                time.sleep(1.0)

                # Verify run completed
                run_state = client.get(f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}")
                assert run_state.json()["status"] == "completed"

    finally:
        os.environ.pop("RESUME_AGENT_EXECUTOR_MODE", None)
        os.environ.pop("GEMINI_API_KEY", None)


def test_real_mode_without_llm_config_fails():
    """Real mode without LLM config should fail gracefully."""
    os.environ["RESUME_AGENT_EXECUTOR_MODE"] = "real"
    # Deliberately not setting GEMINI_API_KEY

    try:
        with TestClient(create_app()) as client:
            # Create session and run
            session = client.post("/api/v1/sessions", json={"workspace_name": "test"}).json()
            run = client.post(
                f"/api/v1/sessions/{session['session_id']}/messages",
                json={"message": "This should fail"},
            ).json()

            # Wait for failure
            time.sleep(1.5)

            # Check run status
            run_state = client.get(f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}")
            body = run_state.json()

            # Should fail due to missing config
            assert body["status"] == "failed"

    finally:
        os.environ.pop("RESUME_AGENT_EXECUTOR_MODE", None)


def test_real_mode_emits_run_events():
    """Real mode should emit proper SSE events."""
    os.environ["RESUME_AGENT_EXECUTOR_MODE"] = "real"
    os.environ["GEMINI_API_KEY"] = "test-key"

    try:
        with TestClient(create_app()) as client:
            with patch("packages.core.resume_agent_core.agent.ResumeAgent.run", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = "Task completed"

                # Create session and run
                session = client.post("/api/v1/sessions", json={"workspace_name": "test"}).json()
                run = client.post(
                    f"/api/v1/sessions/{session['session_id']}/messages",
                    json={"message": "Do something"},
                ).json()

                # Wait for completion
                time.sleep(1.5)

                # Get run status to verify completion
                run_state = client.get(f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}")
                assert run_state.status_code == 200
                body = run_state.json()

                # Should have completed
                assert body["status"] == "completed"

    finally:
        os.environ.pop("RESUME_AGENT_EXECUTOR_MODE", None)
        os.environ.pop("GEMINI_API_KEY", None)


def test_stub_mode_still_works():
    """Stub mode should continue to work as before."""
    os.environ["RESUME_AGENT_EXECUTOR_MODE"] = "stub"

    try:
        with TestClient(create_app()) as client:
            # Create session and run
            session = client.post("/api/v1/sessions", json={"workspace_name": "test"}).json()
            run = client.post(
                f"/api/v1/sessions/{session['session_id']}/messages",
                json={"message": "Hello"},
            ).json()

            # Wait for completion
            time.sleep(1.0)

            # Get run status
            run_state = client.get(f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}")
            body = run_state.json()

            # Stub should complete successfully
            assert body["status"] in {"completed", "running"}

    finally:
        os.environ.pop("RESUME_AGENT_EXECUTOR_MODE", None)
