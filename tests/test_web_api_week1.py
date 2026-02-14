"""Week 1+2 Web API contract tests."""

from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from resume_agent.web.app import create_app


def _extract_envelopes(raw_stream: str) -> list[dict]:
    envelopes: list[dict] = []
    for block in raw_stream.split("\n\n"):
        if not block.strip():
            continue
        for line in block.splitlines():
            if line.startswith("data: "):
                envelopes.append(json.loads(line[len("data: ") :]))
                break
    return envelopes


def _stream_envelopes(client: TestClient, session_id: str, run_id: str) -> list[dict]:
    with client.stream(
        "GET",
        f"/api/v1/sessions/{session_id}/runs/{run_id}/stream",
    ) as response:
        assert response.status_code == 200
        raw_stream = "".join(response.iter_text())
    return _extract_envelopes(raw_stream)


def _wait_for_pending_approval(client: TestClient, session_id: str, timeout_seconds: float = 2.0) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = client.get(f"/api/v1/sessions/{session_id}/approvals")
        assert response.status_code == 200
        items = response.json()["items"]
        if items:
            return items[0]
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for pending approval")


def test_create_and_get_session() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/sessions",
            json={"workspace_name": "my-resume", "auto_approve": False},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["session_id"].startswith("sess_")
        assert body["workflow_state"] == "draft"
        assert body["settings"] == {"auto_approve": False}
        assert body["created_at"].endswith("Z")

        get_response = client.get(f"/api/v1/sessions/{body['session_id']}")
        assert get_response.status_code == 200
        get_body = get_response.json()
        assert get_body["session_id"] == body["session_id"]
        assert get_body["active_run_id"] is None
        assert get_body["pending_approvals_count"] == 0


def test_create_message_returns_run_id() -> None:
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()

        response = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": "Summarize this resume"},
        )
        assert response.status_code == 202
        body = response.json()
        assert body["run_id"].startswith("run_")
        assert body["status"] in {"queued", "running", "completed"}


def test_stream_returns_contract_compliant_events() -> None:
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()
        run = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": "Summarize resume content"},
        ).json()

        envelopes = _stream_envelopes(client, session["session_id"], run["run_id"])
        assert len(envelopes) >= 2

        event_ids = [event["event_id"] for event in envelopes]
        assert event_ids == sorted(event_ids)

        for event in envelopes:
            assert event["session_id"] == session["session_id"]
            assert event["run_id"] == run["run_id"]
            assert {"event_id", "session_id", "run_id", "type", "ts", "payload"} <= set(event.keys())

        assert envelopes[0]["type"] == "run_started"
        assert envelopes[-1]["type"] == "run_completed"


def test_approve_flow_emits_expected_order() -> None:
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={"auto_approve": False}).json()
        target_path = "frontend-resume-improved-2026-02-03.md"
        run = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": f"Update {target_path}"},
        ).json()

        approval = _wait_for_pending_approval(client, session["session_id"])
        assert approval["args"]["path"] == target_path
        approve_response = client.post(
            f"/api/v1/sessions/{session['session_id']}/approvals/{approval['approval_id']}/approve",
            json={"apply_to_future": False},
        )
        assert approve_response.status_code == 200
        assert approve_response.json()["status"] == "approved"

        envelopes = _stream_envelopes(client, session["session_id"], run["run_id"])
        event_types = [event["type"] for event in envelopes]

        assert "tool_call_proposed" in event_types
        assert "tool_call_approved" in event_types
        assert "tool_result" in event_types
        assert event_types.index("tool_call_proposed") < event_types.index("tool_call_approved")
        assert event_types.index("tool_call_approved") < event_types.index("tool_result")
        assert event_types[-1] == "run_completed"
        tool_result = next(event for event in envelopes if event["type"] == "tool_result")
        assert target_path in tool_result["payload"]["result"]

        session_state = client.get(f"/api/v1/sessions/{session['session_id']}").json()
        assert session_state["pending_approvals_count"] == 0


def test_reject_flow_completes_without_tool_result() -> None:
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={"auto_approve": False}).json()
        run = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": "Edit frontend-resume-improved-2026-02-03.md"},
        ).json()

        approval = _wait_for_pending_approval(client, session["session_id"])
        reject_response = client.post(
            f"/api/v1/sessions/{session['session_id']}/approvals/{approval['approval_id']}/reject",
        )
        assert reject_response.status_code == 200
        assert reject_response.json()["status"] == "rejected"

        envelopes = _stream_envelopes(client, session["session_id"], run["run_id"])
        event_types = [event["type"] for event in envelopes]

        assert "tool_call_proposed" in event_types
        assert "tool_call_rejected" in event_types
        assert "tool_result" not in event_types
        assert event_types[-1] == "run_completed"

        run_state = client.get(
            f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}"
        ).json()
        assert run_state["status"] == "completed"


def test_interrupt_flow_returns_interrupted_terminal_event() -> None:
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()
        run = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": "Run a long analysis"},
        ).json()

        interrupt_response = client.post(
            f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}/interrupt"
        )
        assert interrupt_response.status_code in {200, 202}

        envelopes = _stream_envelopes(client, session["session_id"], run["run_id"])
        event_types = [event["type"] for event in envelopes]

        assert event_types[0] == "run_started"
        assert "run_interrupted" in event_types
        assert event_types[-1] == "run_interrupted"

        run_state = client.get(
            f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}"
        ).json()
        assert run_state["status"] == "interrupted"


def test_approval_double_process_returns_409() -> None:
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={"auto_approve": False}).json()
        run = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": "Modify frontend-resume-improved-2026-02-03.md"},
        ).json()

        approval = _wait_for_pending_approval(client, session["session_id"])
        first = client.post(
            f"/api/v1/sessions/{session['session_id']}/approvals/{approval['approval_id']}/approve",
            json={"apply_to_future": False},
        )
        assert first.status_code == 200

        second = client.post(
            f"/api/v1/sessions/{session['session_id']}/approvals/{approval['approval_id']}/approve",
            json={"apply_to_future": False},
        )
        assert second.status_code == 409

        # Drain events so the run reaches terminal state before test cleanup.
        _stream_envelopes(client, session["session_id"], run["run_id"])


def test_interrupt_terminal_run_returns_200_with_current_status() -> None:
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()
        run = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": "Summarize resume content"},
        ).json()

        _stream_envelopes(client, session["session_id"], run["run_id"])
        interrupt = client.post(
            f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}/interrupt"
        )
        assert interrupt.status_code == 200
        assert interrupt.json()["status"] == "completed"


def test_set_auto_approve_endpoint_updates_session_settings() -> None:
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={"auto_approve": False}).json()

        update = client.post(
            f"/api/v1/sessions/{session['session_id']}/settings/auto-approve",
            json={"enabled": True},
        )
        assert update.status_code == 200
        assert update.json() == {"enabled": True}

        session_state = client.get(f"/api/v1/sessions/{session['session_id']}").json()
        assert session_state["settings"]["auto_approve"] is True

        run = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": "Update frontend-resume-improved-2026-02-03.md"},
        ).json()
        envelopes = _stream_envelopes(client, session["session_id"], run["run_id"])
        event_types = [event["type"] for event in envelopes]
        assert "tool_result" in event_types
        assert "tool_call_proposed" not in event_types

        approvals = client.get(f"/api/v1/sessions/{session['session_id']}/approvals").json()
        assert approvals["items"] == []


def test_stream_last_event_id_replays_from_next_event() -> None:
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()
        run = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": "Summarize resume content"},
        ).json()

        all_events = _stream_envelopes(client, session["session_id"], run["run_id"])
        assert len(all_events) >= 2
        first_event_id = all_events[0]["event_id"]

        with client.stream(
            "GET",
            f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}/stream",
            headers={"Last-Event-ID": first_event_id},
        ) as response:
            assert response.status_code == 200
            replay_events = _extract_envelopes("".join(response.iter_text()))

        assert replay_events
        assert replay_events[0]["event_id"] == all_events[1]["event_id"]
        assert len(replay_events) == len(all_events) - 1


def test_missing_resources_return_contract_errors() -> None:
    with TestClient(create_app()) as client:
        missing_run = client.get("/api/v1/sessions/sess_missing/runs/run_missing")
        assert missing_run.status_code == 404
        missing_run_error = missing_run.json()["error"]
        assert missing_run_error["code"] == "SESSION_NOT_FOUND"
        assert "message" in missing_run_error
        assert "details" in missing_run_error

        session = client.post("/api/v1/sessions", json={}).json()
        missing_approval = client.post(
            f"/api/v1/sessions/{session['session_id']}/approvals/appr_missing/approve",
            json={"apply_to_future": False},
        )
        assert missing_approval.status_code == 404
        missing_approval_error = missing_approval.json()["error"]
        assert missing_approval_error["code"] == "APPROVAL_NOT_FOUND"
        assert "message" in missing_approval_error
        assert "details" in missing_approval_error
