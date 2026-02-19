"""Tests for SQLiteRuntimeStore — persistence, lifecycle, normalization."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import pytest_asyncio

from apps.api.resume_agent_api.errors import APIError
from apps.api.resume_agent_api.sqlite_store import SQLiteRuntimeStore
from apps.api.resume_agent_api.workspace import RemoteWorkspaceProvider


@pytest_asyncio.fixture
async def tmp_store(tmp_path: Path):
    """Create a SQLiteRuntimeStore backed by a temp directory."""
    db_path = tmp_path / "test.db"
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()
    workspace_provider = RemoteWorkspaceProvider(workspace_root)
    store = SQLiteRuntimeStore(
        db_path=db_path,
        workspace_provider=workspace_provider,
        provider_name="stub",
        model_name="stub-model",
    )
    store._executor_mode = "stub"
    await store.start()
    yield store
    await store.stop()


@pytest_asyncio.fixture
async def store_factory(tmp_path: Path):
    """Factory that creates stores sharing the same DB path (for restart tests)."""
    db_path = tmp_path / "shared.db"
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()
    stores: list[SQLiteRuntimeStore] = []

    async def _make(start: bool = True) -> SQLiteRuntimeStore:
        wp = RemoteWorkspaceProvider(workspace_root)
        s = SQLiteRuntimeStore(db_path=db_path, workspace_provider=wp)
        s._executor_mode = "stub"
        if start:
            await s.start()
        stores.append(s)
        return s

    yield _make

    for s in stores:
        try:
            await s.stop()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Session CRUD persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_persists_across_restart(store_factory):
    """Create session → stop store → new store instance → session still there."""
    store1 = await store_factory()
    session = await store1.create_session("ws1", auto_approve=True, tenant_id="t1")
    sid = session.session_id
    await store1.stop()

    store2 = await store_factory()
    recovered = await store2.get_session(sid)
    assert recovered.session_id == sid
    assert recovered.tenant_id == "t1"
    assert recovered.workspace_name == "ws1"
    assert recovered.settings["auto_approve"] is True


@pytest.mark.asyncio
async def test_session_not_found(tmp_store):
    with pytest.raises(APIError) as exc_info:
        await tmp_store.get_session("nonexistent")
    assert exc_info.value.code == "SESSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_tenant_isolation(tmp_store):
    session = await tmp_store.create_session("ws", auto_approve=False, tenant_id="t1")
    with pytest.raises(APIError) as exc_info:
        await tmp_store.get_session(session.session_id, tenant_id="t2")
    assert exc_info.value.code == "SESSION_NOT_FOUND"


# ---------------------------------------------------------------------------
# Run lifecycle persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_lifecycle_persists(store_factory):
    """Run goes queued → running → completed, survives restart."""
    store1 = await store_factory()
    session = await store1.create_session("ws", auto_approve=True, tenant_id="t1")
    run, reused = await store1.create_run(session.session_id, "hello", idempotency_key=None)
    assert not reused
    assert run.status == "queued"

    # Wait for stub run to complete
    for _ in range(100):
        r = await store1.get_run(session.session_id, run.run_id)
        if r.status == "completed":
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail("Run did not complete in time")

    await store1.stop()

    # Reopen and verify
    store2 = await store_factory()
    recovered = await store2.get_run(session.session_id, run.run_id)
    assert recovered.status == "completed"
    assert recovered.usage_tokens > 0
    assert len(recovered.events) > 0


# ---------------------------------------------------------------------------
# Restart normalization — active runs → interrupted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_runs_normalized_on_restart(store_factory):
    """If a run is still active when the store restarts, it becomes interrupted."""
    store1 = await store_factory()
    session = await store1.create_session("ws", auto_approve=True, tenant_id="t1")

    # Insert a run directly as 'running' to simulate crash mid-run
    import aiosqlite  # noqa: F401

    from apps.api.resume_agent_api.store import utc_now_iso

    now = utc_now_iso()
    await store1._db.execute(
        "INSERT INTO runs (run_id, session_id, message, status, created_at, started_at)"
        " VALUES (?, ?, ?, 'running', ?, ?)",
        ("run_crash", session.session_id, "test", now, now),
    )
    await store1._db.execute(
        "UPDATE sessions SET active_run_id = 'run_crash' WHERE session_id = ?",
        (session.session_id,),
    )
    await store1._db.commit()

    # Force-close without clean shutdown
    await store1._db.close()
    store1._db = None
    store1._stop_requested = True
    await store1._run_queue.put((None, None))
    if store1._worker_task:
        await store1._worker_task
        store1._worker_task = None

    # New store instance — normalization should kick in
    store2 = await store_factory()
    run = await store2.get_run(session.session_id, "run_crash")
    assert run.status == "interrupted"
    assert run.interrupt_requested is True
    assert any(e["type"] == "run_interrupted" for e in run.events)

    # Session's active_run_id should be cleared
    s = await store2.get_session(session.session_id)
    assert s.active_run_id is None


# PLACEHOLDER_MORE_TESTS


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotency_key_reuse(tmp_store):
    session = await tmp_store.create_session("ws", auto_approve=True, tenant_id="t1")
    run1, reused1 = await tmp_store.create_run(session.session_id, "msg", idempotency_key="key1")
    assert not reused1

    # Wait for completion
    for _ in range(100):
        r = await tmp_store.get_run(session.session_id, run1.run_id)
        if r.status == "completed":
            break
        await asyncio.sleep(0.05)

    run2, reused2 = await tmp_store.create_run(session.session_id, "msg", idempotency_key="key1")
    assert reused2
    assert run2.run_id == run1.run_id


@pytest.mark.asyncio
async def test_idempotency_conflict(tmp_store):
    session = await tmp_store.create_session("ws", auto_approve=True, tenant_id="t1")
    await tmp_store.create_run(session.session_id, "msg1", idempotency_key="key1")

    # Wait for completion
    for _ in range(100):
        s = await tmp_store.get_session(session.session_id)
        if s.active_run_id is None:
            break
        await asyncio.sleep(0.05)

    with pytest.raises(APIError) as exc_info:
        await tmp_store.create_run(session.session_id, "different msg", idempotency_key="key1")
    assert exc_info.value.code == "IDEMPOTENCY_CONFLICT"


# ---------------------------------------------------------------------------
# Events persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_events_persist(store_factory):
    store1 = await store_factory()
    session = await store1.create_session("ws", auto_approve=True, tenant_id="t1")
    run, _ = await store1.create_run(session.session_id, "hello", idempotency_key=None)

    # Wait for completion
    for _ in range(100):
        r = await store1.get_run(session.session_id, run.run_id)
        if r.status == "completed":
            break
        await asyncio.sleep(0.05)

    events1, status1 = await store1.snapshot_events(session.session_id, run.run_id)
    assert status1 == "completed"
    assert len(events1) > 0

    await store1.stop()

    store2 = await store_factory()
    events2, status2 = await store2.snapshot_events(session.session_id, run.run_id)
    assert status2 == "completed"
    assert len(events2) == len(events1)


# ---------------------------------------------------------------------------
# Usage and metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_usage(tmp_store):
    session = await tmp_store.create_session("ws", auto_approve=True, tenant_id="t1")
    run, _ = await tmp_store.create_run(session.session_id, "hello", idempotency_key=None)

    for _ in range(100):
        r = await tmp_store.get_run(session.session_id, run.run_id)
        if r.status == "completed":
            break
        await asyncio.sleep(0.05)

    usage = await tmp_store.get_session_usage(session.session_id)
    assert usage["run_count"] == 1
    assert usage["completed_run_count"] == 1
    assert usage["total_tokens"] > 0


@pytest.mark.asyncio
async def test_runtime_metrics(tmp_store):
    metrics = await tmp_store.get_runtime_metrics()
    assert "sessions" in metrics
    assert "runs_total" in metrics
    assert "queue_depth" in metrics


# ---------------------------------------------------------------------------
# Workflow state promotion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_promotion(tmp_store):
    session = await tmp_store.create_session("ws", auto_approve=True, tenant_id="t1")
    assert session.workflow_state == "draft"

    # Upload resume
    await tmp_store._workspace_provider.create_workspace(session.session_id, "ws")
    await tmp_store.upload_session_file(
        session.session_id,
        "resume.md",
        b"# My Resume",
        mime_type="text/markdown",
    )
    await tmp_store.upload_resume(
        session.session_id,
        "resume.md",
        b"# My Resume",
        mime_type="text/markdown",
    )
    s = await tmp_store.get_session(session.session_id)
    assert s.workflow_state == "resume_uploaded"
    assert s.resume_path is not None


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_expired_sessions(tmp_store):
    tmp_store.session_ttl_seconds = 0.1  # Reduce wait time
    session = await tmp_store.create_session("ws", auto_approve=True, tenant_id="t1")

    # Wait for TTL to expire
    await asyncio.sleep(0.15)

    result = await tmp_store.cleanup_expired_resources()
    assert result["removed_sessions"] == 1

    with pytest.raises(APIError) as exc_info:
        await tmp_store.get_session(session.session_id)
    assert exc_info.value.code == "SESSION_NOT_FOUND"
