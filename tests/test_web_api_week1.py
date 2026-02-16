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
        assert get_body["usage"]["total_tokens"] == 0
        assert get_body["usage"]["total_estimated_cost_usd"] == 0.0


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


def test_get_run_exposes_usage_telemetry_after_completion() -> None:
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()
        run = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": "Summarize this resume"},
        ).json()
        _stream_envelopes(client, session["session_id"], run["run_id"])

        run_state = client.get(f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}")
        assert run_state.status_code == 200
        body = run_state.json()
        assert body["usage_tokens"] > 0
        assert body["estimated_cost_usd"] >= 0.0

        usage = client.get(f"/api/v1/sessions/{session['session_id']}/usage")
        assert usage.status_code == 200
        usage_body = usage.json()
        assert usage_body["run_count"] == 1
        assert usage_body["completed_run_count"] == 1
        assert usage_body["total_tokens"] == body["usage_tokens"]


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

        run_state = client.get(f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}").json()
        assert run_state["status"] == "completed"


def test_interrupt_flow_returns_interrupted_terminal_event() -> None:
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()
        run = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": "Run a long analysis"},
        ).json()

        interrupt_response = client.post(f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}/interrupt")
        assert interrupt_response.status_code in {200, 202}

        envelopes = _stream_envelopes(client, session["session_id"], run["run_id"])
        event_types = [event["type"] for event in envelopes]

        assert event_types[0] == "run_started"
        assert "run_interrupted" in event_types
        assert event_types[-1] == "run_interrupted"

        run_state = client.get(f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}").json()
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
        interrupt = client.post(f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}/interrupt")
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


def test_upload_list_and_get_file() -> None:
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()
        file_content = b"# Resume\nHello"

        upload = client.post(
            f"/api/v1/sessions/{session['session_id']}/files/upload",
            files={"file": ("resume.md", file_content, "text/markdown")},
        )
        assert upload.status_code == 201
        upload_body = upload.json()
        assert upload_body["file_id"].startswith("file_")
        assert upload_body["path"] == "resume.md"
        assert upload_body["size"] == len(file_content)

        listing = client.get(f"/api/v1/sessions/{session['session_id']}/files")
        assert listing.status_code == 200
        files = listing.json()["files"]
        assert len(files) == 1
        assert files[0]["path"] == "resume.md"
        assert files[0]["size"] == len(file_content)

        download = client.get(f"/api/v1/sessions/{session['session_id']}/files/resume.md")
        assert download.status_code == 200
        assert download.text == "# Resume\nHello"


def test_get_file_rejects_path_escape() -> None:
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()

        response = client.get(f"/api/v1/sessions/{session['session_id']}/files/%2E%2E/secrets.txt")
        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "INVALID_PATH"


def test_api_logs_include_observability_fields(caplog) -> None:
    caplog.set_level("INFO", logger="resume_agent.web.api")
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()
        run = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": "Summarize resume content"},
        ).json()
        client.get(f"/api/v1/sessions/{session['session_id']}/runs/{run['run_id']}")

    assert caplog.records
    # One log line for run-status request should include all key fields.
    assert any(
        "session_id=" in record.message
        and "run_id=" in record.message
        and "provider=" in record.message
        and "model=" in record.message
        and "retry_max_attempts=" in record.message
        and "fallback_chain_size=" in record.message
        for record in caplog.records
    )


def test_provider_policy_endpoint_returns_configured_values(monkeypatch) -> None:
    monkeypatch.setenv("RESUME_AGENT_WEB_PROVIDER_RETRY_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("RESUME_AGENT_WEB_PROVIDER_RETRY_BASE_DELAY_SECONDS", "0.2")
    monkeypatch.setenv("RESUME_AGENT_WEB_PROVIDER_RETRY_MAX_DELAY_SECONDS", "2.5")
    monkeypatch.setenv(
        "RESUME_AGENT_WEB_PROVIDER_FALLBACK_CHAIN",
        "openai:gpt-4o-mini,gemini:gemini-2.5-flash",
    )
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/settings/provider-policy")
        assert response.status_code == 200
        body = response.json()
        assert body["retry"] == {
            "max_attempts": 5,
            "base_delay_seconds": 0.2,
            "max_delay_seconds": 2.5,
        }
        assert body["fallback_chain"] == [
            {"provider": "openai", "model": "gpt-4o-mini"},
            {"provider": "gemini", "model": "gemini-2.5-flash"},
        ]


def test_resume_and_jd_workflow_transitions() -> None:
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()
        session_id = session["session_id"]

        resume_upload = client.post(
            f"/api/v1/sessions/{session_id}/resume",
            files={"file": ("resume.md", b"# Resume", "text/markdown")},
        )
        assert resume_upload.status_code == 201
        assert resume_upload.json()["workflow_state"] == "resume_uploaded"

        jd_submit = client.post(
            f"/api/v1/sessions/{session_id}/jd",
            json={"text": "Looking for frontend engineer with TypeScript skills"},
        )
        assert jd_submit.status_code == 200
        assert jd_submit.json()["workflow_state"] == "jd_provided"

        state = client.get(f"/api/v1/sessions/{session_id}").json()
        assert state["workflow_state"] == "jd_provided"
        assert state["resume_path"] == "resume.md"
        assert state["jd_text"] is not None


def test_jd_requires_resume_upload_first() -> None:
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()
        response = client.post(
            f"/api/v1/sessions/{session['session_id']}/jd",
            json={"text": "Frontend JD"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "INVALID_STATE"


def test_write_run_updates_file_and_workflow_state() -> None:
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={"auto_approve": True}).json()
        session_id = session["session_id"]

        client.post(
            f"/api/v1/sessions/{session_id}/resume",
            files={"file": ("resume.md", b"# Resume\\nOriginal", "text/markdown")},
        )
        client.post(
            f"/api/v1/sessions/{session_id}/jd",
            json={"text": "Frontend engineer JD"},
        )

        run = client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"message": "Update resume.md to add impact metrics"},
        ).json()
        envelopes = _stream_envelopes(client, session_id, run["run_id"])
        assert any(event["type"] == "tool_result" for event in envelopes)

        updated = client.get(f"/api/v1/sessions/{session_id}/files/resume.md")
        assert updated.status_code == 200
        assert "Updated by run" in updated.text

        state = client.get(f"/api/v1/sessions/{session_id}").json()
        assert state["workflow_state"] == "rewrite_applied"


def test_export_endpoint_creates_artifact_and_marks_exported() -> None:
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()
        session_id = session["session_id"]

        client.post(
            f"/api/v1/sessions/{session_id}/resume",
            files={"file": ("resume.md", b"# Resume\\nSample", "text/markdown")},
        )
        export = client.post(f"/api/v1/sessions/{session_id}/export")
        assert export.status_code == 201
        body = export.json()
        assert body["artifact_path"].startswith("exports/")
        assert body["workflow_state"] == "exported"

        encoded = body["artifact_path"].replace("/", "%2F")
        artifact = client.get(f"/api/v1/sessions/{session_id}/files/{encoded}")
        assert artifact.status_code == 200
        assert artifact.text.startswith("# Exported Resume")

        state = client.get(f"/api/v1/sessions/{session_id}").json()
        assert state["latest_export_path"] == body["artifact_path"]
        assert state["workflow_state"] == "exported"


def test_cleanup_endpoint_removes_expired_artifacts_without_dropping_session(monkeypatch) -> None:
    monkeypatch.setenv("RESUME_AGENT_WEB_ARTIFACT_TTL_SECONDS", "1")
    monkeypatch.setenv("RESUME_AGENT_WEB_SESSION_TTL_SECONDS", "0")
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()
        session_id = session["session_id"]
        client.post(
            f"/api/v1/sessions/{session_id}/resume",
            files={"file": ("resume.md", b"# Resume", "text/markdown")},
        )
        export = client.post(f"/api/v1/sessions/{session_id}/export")
        assert export.status_code == 201
        artifact_path = export.json()["artifact_path"]
        time.sleep(2.1)

        cleanup = client.post("/api/v1/settings/cleanup")
        assert cleanup.status_code == 200
        assert cleanup.json()["removed_artifact_files"] >= 1

        encoded = artifact_path.replace("/", "%2F")
        missing_artifact = client.get(f"/api/v1/sessions/{session_id}/files/{encoded}")
        assert missing_artifact.status_code == 404
        # Session itself still exists since session TTL is disabled.
        assert client.get(f"/api/v1/sessions/{session_id}").status_code == 200


def test_cleanup_endpoint_removes_expired_sessions(monkeypatch) -> None:
    monkeypatch.setenv("RESUME_AGENT_WEB_SESSION_TTL_SECONDS", "1")
    monkeypatch.setenv("RESUME_AGENT_WEB_ARTIFACT_TTL_SECONDS", "0")
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()
        session_id = session["session_id"]
        time.sleep(2.1)

        cleanup = client.post("/api/v1/settings/cleanup")
        assert cleanup.status_code == 200
        assert cleanup.json()["removed_sessions"] >= 1
        missing = client.get(f"/api/v1/sessions/{session_id}")
        assert missing.status_code == 404


def test_web_ui_page_served() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/web")
        assert response.status_code == 200
        assert "Phase 2" in response.text


def test_tenant_isolation_blocks_cross_tenant_access() -> None:
    with TestClient(create_app()) as client:
        create = client.post(
            "/api/v1/sessions",
            json={},
            headers={"X-Tenant-ID": "tenant-a"},
        )
        assert create.status_code == 201
        session_id = create.json()["session_id"]

        own = client.get(
            f"/api/v1/sessions/{session_id}",
            headers={"X-Tenant-ID": "tenant-a"},
        )
        assert own.status_code == 200

        cross = client.get(
            f"/api/v1/sessions/{session_id}",
            headers={"X-Tenant-ID": "tenant-b"},
        )
        assert cross.status_code == 404
        assert cross.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_token_auth_mode_requires_bearer_and_tenant(monkeypatch) -> None:
    monkeypatch.setenv("RESUME_AGENT_WEB_AUTH_MODE", "token")
    monkeypatch.setenv("RESUME_AGENT_WEB_API_TOKEN", "secret-token")
    with TestClient(create_app()) as client:
        missing = client.post("/api/v1/sessions", json={})
        assert missing.status_code == 401
        assert missing.json()["error"]["code"] == "UNAUTHORIZED"

        no_tenant = client.post(
            "/api/v1/sessions",
            json={},
            headers={"Authorization": "Bearer secret-token"},
        )
        assert no_tenant.status_code == 400

        ok = client.post(
            "/api/v1/sessions",
            json={},
            headers={
                "Authorization": "Bearer secret-token",
                "X-Tenant-ID": "tenant-a",
            },
        )
        assert ok.status_code == 201


def test_rate_limit_returns_429(monkeypatch) -> None:
    monkeypatch.setenv("RESUME_AGENT_WEB_RATE_LIMIT_RPM", "1")
    with TestClient(create_app()) as client:
        create = client.post("/api/v1/sessions", json={})
        assert create.status_code == 201
        second = client.get(f"/api/v1/sessions/{create.json()['session_id']}")
        assert second.status_code == 429
        assert second.json()["error"]["code"] == "RATE_LIMITED"


def test_session_run_quota_enforced(monkeypatch) -> None:
    monkeypatch.setenv("RESUME_AGENT_WEB_MAX_RUNS_PER_SESSION", "1")
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()
        run = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": "Summarize resume content"},
        )
        assert run.status_code == 202
        _stream_envelopes(client, session["session_id"], run.json()["run_id"])

        second = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": "Another run"},
        )
        assert second.status_code == 429
        assert second.json()["error"]["code"] == "SESSION_RUN_QUOTA_EXCEEDED"


def test_idempotency_reuse_works_even_after_session_quota_reached(monkeypatch) -> None:
    monkeypatch.setenv("RESUME_AGENT_WEB_MAX_RUNS_PER_SESSION", "1")
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()
        first = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": "Summarize resume content", "idempotency_key": "msg-1"},
        )
        assert first.status_code == 202
        run_id = first.json()["run_id"]
        _stream_envelopes(client, session["session_id"], run_id)

        reused = client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={"message": "Summarize resume content", "idempotency_key": "msg-1"},
        )
        assert reused.status_code == 202
        assert reused.json()["run_id"] == run_id


def test_upload_constraints_enforced(monkeypatch) -> None:
    monkeypatch.setenv("RESUME_AGENT_WEB_MAX_UPLOAD_BYTES", "8")
    with TestClient(create_app()) as client:
        session = client.post("/api/v1/sessions", json={}).json()
        too_large = client.post(
            f"/api/v1/sessions/{session['session_id']}/files/upload",
            files={"file": ("resume.md", b"123456789", "text/markdown")},
        )
        assert too_large.status_code == 422
        assert too_large.json()["error"]["code"] == "UPLOAD_TOO_LARGE"

        bad_type = client.post(
            f"/api/v1/sessions/{session['session_id']}/files/upload",
            files={"file": ("resume.png", b"abc", "image/png")},
        )
        assert bad_type.status_code == 422
        assert bad_type.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
