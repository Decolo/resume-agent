"""Week 1 Web API contract tests."""

from __future__ import annotations

import json

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
            json={"message": "Update resume summary"},
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
            json={"message": "Make one edit"},
        ).json()

        with client.stream(
            "GET",
            f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}/stream",
        ) as response:
            assert response.status_code == 200
            raw_stream = "".join(response.iter_text())

        envelopes = _extract_envelopes(raw_stream)
        assert len(envelopes) >= 2

        event_ids = [event["event_id"] for event in envelopes]
        assert event_ids == sorted(event_ids)

        for event in envelopes:
            assert event["session_id"] == session["session_id"]
            assert event["run_id"] == run["run_id"]
            assert {"event_id", "session_id", "run_id", "type", "ts", "payload"} <= set(event.keys())

        assert envelopes[0]["type"] == "run_started"
        assert envelopes[-1]["type"] == "run_completed"
