"""Persistence behavior tests for Web API runtime store."""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.resume_agent_api.app import create_app


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


def _wait_for_pending_approval(client: TestClient, session_id: str) -> dict:
    deadline = time.time() + 5.0
    while time.time() < deadline:
        response = client.get(f"/api/v1/sessions/{session_id}/approvals")
        assert response.status_code == 200
        items = response.json()["items"]
        if items:
            return items[0]
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for pending approval")


def test_runtime_state_persists_session_workflow_and_run_events(monkeypatch, tmp_path: Path) -> None:
    state_file = tmp_path / "runtime_state.json"
    monkeypatch.setenv("RESUME_AGENT_WEB_STATE_FILE", str(state_file))

    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={"auto_approve": False}).json()
        session_id = session["session_id"]

        client.post(
            f"/api/v1/sessions/{session_id}/resume",
            files={"file": ("resume.md", b"# Resume", "text/markdown")},
        )
        client.post(
            f"/api/v1/sessions/{session_id}/jd",
            json={"text": "Frontend engineer JD"},
        )

        run = client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"message": "Update resume.md to add measurable metrics"},
        ).json()
        run_id = run["run_id"]

        approval = _wait_for_pending_approval(client, session_id)
        client.post(
            f"/api/v1/sessions/{session_id}/approvals/{approval['approval_id']}/approve",
            json={"apply_to_future": False},
        )
        envelopes = _stream_envelopes(client, session_id, run_id)
        assert envelopes[-1]["type"] == "run_completed"

    assert state_file.exists()
    persisted = json.loads(state_file.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 1

    with TestClient(create_app()) as client:
        restored = client.get(f"/api/v1/sessions/{session_id}")
        assert restored.status_code == 200
        body = restored.json()
        assert body["workflow_state"] == "rewrite_applied"
        assert body["pending_approvals_count"] == 0
        assert body["active_run_id"] is None

        run_state = client.get(f"/api/v1/sessions/{session_id}/runs/{run_id}")
        assert run_state.status_code == 200
        assert run_state.json()["status"] == "completed"

        replay = _stream_envelopes(client, session_id, run_id)
        assert replay[0]["type"] == "run_started"
        assert replay[-1]["type"] == "run_completed"


def test_state_loader_accepts_legacy_payload_without_schema_version(monkeypatch, tmp_path: Path) -> None:
    state_file = tmp_path / "legacy_state.json"
    monkeypatch.setenv("RESUME_AGENT_WEB_STATE_FILE", str(state_file))

    state_file.write_text(
        json.dumps(
            {
                "sessions": [
                    {
                        "session_id": "sess_legacy",
                        "tenant_id": "local-dev",
                        "workspace_name": "legacy-workspace",
                        "created_at": "2026-02-16T00:00:00Z",
                        "workflow_state": "jd_provided",
                        "settings": {"auto_approve": False},
                        "active_run_id": None,
                        "pending_approvals_count": 0,
                        "resume_path": "resume.md",
                        "jd_text": "legacy jd",
                        "jd_url": None,
                        "latest_export_path": None,
                        "runs": [
                            {
                                "run_id": "run_legacy",
                                "session_id": "sess_legacy",
                                "message": "Summarize resume",
                                "status": "completed",
                                "created_at": "2026-02-16T00:00:01Z",
                                "started_at": "2026-02-16T00:00:01Z",
                                "ended_at": "2026-02-16T00:00:02Z",
                                "error": None,
                                "events": [
                                    {
                                        "event_id": "evt_run_legacy_0001",
                                        "session_id": "sess_legacy",
                                        "run_id": "run_legacy",
                                        "type": "run_started",
                                        "ts": "2026-02-16T00:00:01Z",
                                        "payload": {"status": "running"},
                                    },
                                    {
                                        "event_id": "evt_run_legacy_0002",
                                        "session_id": "sess_legacy",
                                        "run_id": "run_legacy",
                                        "type": "run_completed",
                                        "ts": "2026-02-16T00:00:02Z",
                                        "payload": {"status": "completed"},
                                    },
                                ],
                                "event_seq": 2,
                                "interrupt_requested": False,
                                "pending_approval_id": None,
                                "usage_tokens": 10,
                                "estimated_cost_usd": 0.00001,
                                "usage_finalized": True,
                            }
                        ],
                        "approvals": [],
                        "idempotency_keys": {},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with TestClient(create_app()) as client:
        session = client.get("/api/v1/sessions/sess_legacy")
        assert session.status_code == 200
        assert session.json()["workflow_state"] == "jd_provided"

        run = client.get("/api/v1/sessions/sess_legacy/runs/run_legacy")
        assert run.status_code == 200
        assert run.json()["status"] == "completed"

    normalized = json.loads(state_file.read_text(encoding="utf-8"))
    assert normalized["schema_version"] == 1
