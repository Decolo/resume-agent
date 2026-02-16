"""Audit log and redaction policy tests."""

from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from apps.api.resume_agent_api.app import create_app
from apps.api.resume_agent_api.redaction import redact_text


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


def test_redact_text_masks_common_sensitive_patterns() -> None:
    raw = "Email me at colo@example.com, phone +86 130 3360 2037, key sk-1234567890abcdef"
    masked = redact_text(raw)
    assert "colo@example.com" not in masked
    assert "130 3360 2037" not in masked
    assert "sk-1234567890abcdef" not in masked
    assert "[REDACTED_EMAIL]" in masked
    assert "[REDACTED_PHONE]" in masked
    assert "[REDACTED_KEY]" in masked


def test_audit_logs_file_write_and_approval_with_redacted_payload(caplog) -> None:
    caplog.set_level("INFO", logger="resume_agent.web.api")
    caplog.set_level("INFO", logger="resume_agent.web.audit")
    secret_message = (
        "Update resume.md and add contact colo@example.com " "phone +86 130 3360 2037 and token sk-1234567890abcdef"
    )

    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={"auto_approve": False}).json()
        run = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": secret_message},
        ).json()
        approval = _wait_for_pending_approval(client, session["session_id"])
        approve = client.post(
            f"/api/v1/sessions/{session['session_id']}/approvals/{approval['approval_id']}/approve",
            json={"apply_to_future": False},
        )
        assert approve.status_code == 200
        _stream_envelopes(client, session["session_id"], run["run_id"])

    combined_logs = "\n".join(record.message for record in caplog.records)
    assert "action=approval_decided" in combined_logs
    assert "action=file_written" in combined_logs
    assert "colo@example.com" not in combined_logs
    assert "130 3360 2037" not in combined_logs
    assert "sk-1234567890abcdef" not in combined_logs
    assert "[REDACTED_EMAIL]" in combined_logs
    assert "[REDACTED_PHONE]" in combined_logs
    assert "[REDACTED_KEY]" in combined_logs
