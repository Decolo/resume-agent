"""SQLite-backed runtime store for Web API — durable across restarts."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import aiosqlite

from packages.contracts.resume_agent_contracts.web.runtime import (
    ACTIVE_RUN_STATES,
    DEFAULT_ALLOWED_UPLOAD_MIME_TYPES,
    DEFAULT_COST_PER_MILLION_TOKENS,
    TERMINAL_RUN_STATES,
    WORKFLOW_ORDER,
)

from .artifact_storage import ArtifactStorageProvider
from .errors import APIError
from .redaction import redact_for_log
from .store import ApprovalRecord, RunRecord, SessionRecord, make_id, utc_now_iso
from .workspace import WorkspaceFile, WorkspaceFileContent, WorkspaceProvider

WRITE_INTENT_KEYWORDS = ("write", "update", "modify", "edit", "create", "copy")
logger = logging.getLogger("resume_agent.web.api")
audit_logger = logging.getLogger("resume_agent.web.audit")

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    workspace_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    workflow_state TEXT NOT NULL DEFAULT 'draft',
    settings_json TEXT NOT NULL DEFAULT '{}',
    active_run_id TEXT,
    pending_approvals_count INTEGER DEFAULT 0,
    resume_path TEXT,
    jd_text TEXT,
    jd_url TEXT,
    latest_export_path TEXT,
    idempotency_keys_json TEXT DEFAULT '{}',
    conversation_json TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    message TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    error_json TEXT,
    events_json TEXT DEFAULT '[]',
    event_seq INTEGER DEFAULT 0,
    interrupt_requested INTEGER DEFAULT 0,
    pending_approval_id TEXT,
    usage_tokens INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0.0,
    usage_finalized INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    run_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    args_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_approvals_session ON approvals(session_id);
"""

# ---------------------------------------------------------------------------
# Helper: row → record
# ---------------------------------------------------------------------------


def _row_to_session(row: aiosqlite.Row) -> SessionRecord:
    """Map a sessions table row to a SessionRecord (no runs/approvals)."""
    settings = json.loads(row["settings_json"]) if row["settings_json"] else {}
    raw_idem = json.loads(row["idempotency_keys_json"]) if row["idempotency_keys_json"] else {}
    idempotency_keys: Dict[str, Tuple[str, str]] = {}
    for k, v in raw_idem.items():
        if isinstance(v, (list, tuple)) and len(v) == 2:
            idempotency_keys[k] = (str(v[0]), str(v[1]))
    return SessionRecord(
        session_id=row["session_id"],
        tenant_id=row["tenant_id"],
        workspace_name=row["workspace_name"],
        created_at=row["created_at"],
        workflow_state=row["workflow_state"],
        settings=settings,
        active_run_id=row["active_run_id"],
        pending_approvals_count=row["pending_approvals_count"] or 0,
        resume_path=row["resume_path"],
        jd_text=row["jd_text"],
        jd_url=row["jd_url"],
        latest_export_path=row["latest_export_path"],
        idempotency_keys=idempotency_keys,
    )


def _row_to_run(row: aiosqlite.Row) -> RunRecord:
    events = json.loads(row["events_json"]) if row["events_json"] else []
    error = json.loads(row["error_json"]) if row["error_json"] else None
    return RunRecord(
        run_id=row["run_id"],
        session_id=row["session_id"],
        message=row["message"],
        status=row["status"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        error=error,
        events=events,
        event_seq=row["event_seq"] or 0,
        interrupt_requested=bool(row["interrupt_requested"]),
        pending_approval_id=row["pending_approval_id"],
        usage_tokens=row["usage_tokens"] or 0,
        estimated_cost_usd=row["estimated_cost_usd"] or 0.0,
        usage_finalized=bool(row["usage_finalized"]),
    )


def _row_to_approval(row: aiosqlite.Row) -> ApprovalRecord:
    args = json.loads(row["args_json"]) if row["args_json"] else {}
    return ApprovalRecord(
        approval_id=row["approval_id"],
        session_id=row["session_id"],
        run_id=row["run_id"],
        tool_name=row["tool_name"],
        args=args,
        created_at=row["created_at"],
        status=row["status"],
        decided_at=row["decided_at"],
    )


# PLACEHOLDER_CLASS_START


class SQLiteRuntimeStore:
    """SQLite-backed runtime store — survives process restarts."""

    def __init__(
        self,
        db_path: Path,
        workspace_provider: WorkspaceProvider,
        artifact_storage_provider: Optional[ArtifactStorageProvider] = None,
        provider_name: str = "stub",
        model_name: str = "stub-model",
        max_runs_per_session: int = 100,
        max_upload_bytes: int = 5 * 1024 * 1024,
        allowed_upload_mime_types: Optional[List[str]] = None,
        cost_per_million_tokens: float = DEFAULT_COST_PER_MILLION_TOKENS,
        session_ttl_seconds: int = 0,
        artifact_ttl_seconds: int = 0,
        cleanup_interval_seconds: int = 300,
        provider_error_policy: Optional[Dict[str, Any]] = None,
        alert_thresholds: Optional[Dict[str, float]] = None,
    ) -> None:
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        # Only non-terminal runs live here (they hold asyncio.Event).
        self._active_runs: Dict[str, RunRecord] = {}
        self._lock = asyncio.Lock()
        self._run_queue: asyncio.Queue[Tuple[Optional[str], Optional[str]]] = asyncio.Queue()
        self._stop_requested = False
        self._worker_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._workspace_provider = workspace_provider
        self._artifact_storage_provider = artifact_storage_provider
        self.provider_name = provider_name
        self.model_name = model_name
        self.max_runs_per_session = max_runs_per_session
        self.max_upload_bytes = max_upload_bytes
        self.allowed_upload_mime_types: Set[str] = set(allowed_upload_mime_types or DEFAULT_ALLOWED_UPLOAD_MIME_TYPES)
        self.cost_per_million_tokens = max(cost_per_million_tokens, 0.0)
        self.session_ttl_seconds = max(session_ttl_seconds, 0)
        self.artifact_ttl_seconds = max(artifact_ttl_seconds, 0)
        self.cleanup_interval_seconds = max(cleanup_interval_seconds, 1)
        self.provider_error_policy = provider_error_policy or {
            "retry": {"max_attempts": 3, "base_delay_seconds": 1.0, "max_delay_seconds": 30.0},
            "fallback_chain": [],
        }
        self.alert_thresholds = alert_thresholds or {
            "max_error_rate": 0.2,
            "max_p95_latency_ms": 15_000.0,
            "max_total_cost_usd": 10.0,
            "max_queue_depth": 50.0,
        }
        self._llm_config: Optional[Any] = None
        self._executor_mode: str = "stub"

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(_SCHEMA_SQL)
        await self._db.commit()
        await self._normalize_active_runs()
        if self._worker_task is None:
            self._stop_requested = False
            self._worker_task = asyncio.create_task(self._run_worker())
        if self._cleanup_task is None and (self.session_ttl_seconds > 0 or self.artifact_ttl_seconds > 0):
            self._cleanup_task = asyncio.create_task(self._cleanup_worker())

    async def stop(self) -> None:
        self._stop_requested = True
        await self._run_queue.put((None, None))
        if self._worker_task:
            await self._worker_task
            self._worker_task = None
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        if self._db:
            await self._db.close()
            self._db = None

    # PLACEHOLDER_SESSIONS

    # -- sessions ------------------------------------------------------------

    async def create_session(self, workspace_name: str, auto_approve: bool, tenant_id: str) -> SessionRecord:
        session_id = make_id("sess")
        await self._workspace_provider.create_workspace(session_id=session_id, workspace_name=workspace_name)
        now = utc_now_iso()
        settings = {"auto_approve": auto_approve}
        await self._db.execute(
            "INSERT INTO sessions (session_id, tenant_id, workspace_name, created_at, workflow_state, settings_json)"
            " VALUES (?, ?, ?, ?, 'draft', ?)",
            (session_id, tenant_id, workspace_name, now, json.dumps(settings)),
        )
        await self._db.commit()
        return SessionRecord(
            session_id=session_id,
            tenant_id=tenant_id,
            workspace_name=workspace_name,
            created_at=now,
            workflow_state="draft",
            settings=settings,
        )

    async def get_session(self, session_id: str, tenant_id: Optional[str] = None) -> SessionRecord:
        async with self._db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise APIError(404, "SESSION_NOT_FOUND", f"Session '{session_id}' not found")
        if tenant_id and row["tenant_id"] != tenant_id:
            raise APIError(404, "SESSION_NOT_FOUND", f"Session '{session_id}' not found")
        return _row_to_session(row)

    async def set_auto_approve(
        self, session_id: str, enabled: bool, tenant_id: Optional[str] = None
    ) -> Dict[str, bool]:
        session = await self.get_session(session_id, tenant_id=tenant_id)
        session.settings["auto_approve"] = enabled
        await self._db.execute(
            "UPDATE sessions SET settings_json = ? WHERE session_id = ?",
            (json.dumps(session.settings), session_id),
        )
        await self._db.commit()
        return {"enabled": enabled}

    async def upload_resume(
        self,
        session_id: str,
        filename: str,
        content: bytes,
        mime_type: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> WorkspaceFile:
        metadata = await self.upload_session_file(
            session_id=session_id,
            filename=filename,
            content=content,
            mime_type=mime_type,
            tenant_id=tenant_id,
        )
        await self.get_session(session_id, tenant_id=tenant_id)
        await self._promote_workflow(session_id, "resume_uploaded")
        await self._db.execute(
            "UPDATE sessions SET resume_path = ? WHERE session_id = ?",
            (metadata.path, session_id),
        )
        await self._db.commit()
        return metadata

    # PLACEHOLDER_SUBMIT_JD

    async def submit_jd(
        self,
        session_id: str,
        text: Optional[str],
        url: Optional[str],
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        normalized_text = (text or "").strip()
        normalized_url = (url or "").strip()
        if not normalized_text and not normalized_url:
            raise APIError(400, "BAD_REQUEST", "Either jd text or jd url is required")

        session = await self.get_session(session_id, tenant_id=tenant_id)
        if not session.resume_path:
            raise APIError(409, "INVALID_STATE", "Resume must be uploaded before submitting JD")

        jd_text = normalized_text or None
        jd_url = normalized_url or None
        await self._promote_workflow(session_id, "jd_provided")
        await self._db.execute(
            "UPDATE sessions SET jd_text = ?, jd_url = ? WHERE session_id = ?",
            (jd_text, jd_url, session_id),
        )
        await self._db.commit()
        session = await self.get_session(session_id)
        return {"workflow_state": session.workflow_state, "jd_text": jd_text, "jd_url": jd_url}

    async def export_session(self, session_id: str, tenant_id: Optional[str] = None) -> WorkspaceFile:
        session = await self.get_session(session_id, tenant_id=tenant_id)
        source_path = session.resume_path
        if not source_path:
            files = await self.list_session_files(session_id=session_id, tenant_id=tenant_id)
            if not files:
                raise APIError(409, "INVALID_STATE", "No files available to export")
            source_path = files[0].path

        source_content = await self.read_session_file(session_id=session_id, file_path=source_path, tenant_id=tenant_id)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        export_name = f"exports/{Path(source_path).stem}-export-{timestamp}.md"
        export_content = self._build_export_content(source_content.content)
        if self._artifact_storage_provider:
            artifact = await self._artifact_storage_provider.write_artifact(
                session_id=session_id,
                artifact_path=export_name,
                content=export_content,
            )
        else:
            artifact = await self._workspace_provider.write_file(
                session_id=session_id,
                relative_path=export_name,
                content=export_content,
            )

        await self._promote_workflow(session_id, "exported")
        await self._db.execute(
            "UPDATE sessions SET latest_export_path = ? WHERE session_id = ?",
            (artifact.path, session_id),
        )
        await self._db.commit()
        await self._audit(
            action="file_exported",
            session_id=session_id,
            details={"artifact_path": artifact.path, "size": artifact.size, "mime_type": artifact.mime_type},
        )
        return artifact

    # PLACEHOLDER_RUNS

    # -- runs ----------------------------------------------------------------

    async def create_run(
        self,
        session_id: str,
        message: str,
        idempotency_key: Optional[str],
        tenant_id: Optional[str] = None,
    ) -> Tuple[RunRecord, bool]:
        message_fingerprint = message.strip()
        session = await self.get_session(session_id, tenant_id=tenant_id)

        if idempotency_key:
            existing = session.idempotency_keys.get(idempotency_key)
            if existing:
                existing_fingerprint, existing_run_id = existing
                if existing_fingerprint != message_fingerprint:
                    raise APIError(409, "IDEMPOTENCY_CONFLICT", "Idempotency key already used with different payload")
                existing_run = await self.get_run(session_id, existing_run_id)
                return existing_run, True

        if session.active_run_id:
            try:
                active_run = await self.get_run(session_id, session.active_run_id)
                if active_run.status in ACTIVE_RUN_STATES:
                    raise APIError(
                        409,
                        "ACTIVE_RUN_EXISTS",
                        "Session already has an active run",
                        {"run_id": active_run.run_id, "status": active_run.status},
                    )
            except APIError as exc:
                if exc.code != "RUN_NOT_FOUND":
                    raise

        # Count existing runs
        async with self._db.execute("SELECT COUNT(*) FROM runs WHERE session_id = ?", (session_id,)) as cursor:
            count_row = await cursor.fetchone()
            run_count = count_row[0] if count_row else 0
        if run_count >= self.max_runs_per_session:
            raise APIError(
                429,
                "SESSION_RUN_QUOTA_EXCEEDED",
                "Per-session run quota exceeded",
                {"limit": self.max_runs_per_session},
            )

        run_id = make_id("run")
        now = utc_now_iso()
        run = RunRecord(
            run_id=run_id,
            session_id=session_id,
            message=message,
            status="queued",
            created_at=now,
        )
        await self._db.execute(
            "INSERT INTO runs (run_id, session_id, message, status, created_at)" " VALUES (?, ?, ?, 'queued', ?)",
            (run_id, session_id, message, now),
        )

        # Update idempotency keys
        if idempotency_key:
            session.idempotency_keys[idempotency_key] = (message_fingerprint, run_id)
        await self._db.execute(
            "UPDATE sessions SET active_run_id = ?, idempotency_keys_json = ? WHERE session_id = ?",
            (run_id, json.dumps(session.idempotency_keys), session_id),
        )
        await self._db.commit()

        async with self._lock:
            self._active_runs[run_id] = run

        await self._run_queue.put((session_id, run_id))
        return run, False

    async def get_run(self, session_id: str, run_id: str, tenant_id: Optional[str] = None) -> RunRecord:
        if tenant_id:
            await self.get_session(session_id, tenant_id=tenant_id)

        # Check in-memory active runs first (has live wait_event)
        async with self._lock:
            active = self._active_runs.get(run_id)
            if active and active.session_id == session_id:
                return active

        # Fall back to DB
        async with self._db.execute(
            "SELECT * FROM runs WHERE run_id = ? AND session_id = ?", (run_id, session_id)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise APIError(404, "RUN_NOT_FOUND", f"Run '{run_id}' not found")
        return _row_to_run(row)

    async def interrupt_run(self, session_id: str, run_id: str, tenant_id: Optional[str] = None) -> RunRecord:
        if tenant_id:
            await self.get_session(session_id, tenant_id=tenant_id)

        run = await self.get_run(session_id, run_id)
        if run.status in TERMINAL_RUN_STATES:
            return run

        run.interrupt_requested = True
        run.status = "interrupting"
        await self._db.execute(
            "UPDATE runs SET status = 'interrupting', interrupt_requested = 1 WHERE run_id = ?",
            (run_id,),
        )
        await self._db.commit()
        run.wait_event.set()
        return run

    # PLACEHOLDER_USAGE

    async def get_session_usage(self, session_id: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        await self.get_session(session_id, tenant_id=tenant_id)
        async with self._db.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN status IN ('completed','failed','interrupted') THEN 1 ELSE 0 END) as completed, "
            "SUM(usage_tokens) as tokens, SUM(estimated_cost_usd) as cost "
            "FROM runs WHERE session_id = ?",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return {
            "run_count": row["total"] or 0,
            "completed_run_count": row["completed"] or 0,
            "total_tokens": row["tokens"] or 0,
            "total_estimated_cost_usd": round(row["cost"] or 0.0, 8),
        }

    async def get_runtime_metrics(self) -> Dict[str, Any]:
        async with self._db.execute("SELECT COUNT(*) FROM sessions") as cur:
            session_count = (await cur.fetchone())[0]
        queue_depth = self._run_queue.qsize()

        async with self._db.execute(
            "SELECT status, COUNT(*) as cnt, SUM(usage_tokens) as tokens, "
            "SUM(estimated_cost_usd) as cost FROM runs GROUP BY status"
        ) as cur:
            status_rows = await cur.fetchall()

        runs_total = runs_active = runs_completed = runs_failed = runs_interrupted = 0
        total_tokens = 0
        total_cost = 0.0
        for r in status_rows:
            cnt = r["cnt"]
            runs_total += cnt
            if r["status"] in ACTIVE_RUN_STATES:
                runs_active += cnt
            elif r["status"] == "completed":
                runs_completed += cnt
            elif r["status"] == "failed":
                runs_failed += cnt
            elif r["status"] == "interrupted":
                runs_interrupted += cnt
            total_tokens += r["tokens"] or 0
            total_cost += r["cost"] or 0.0

        terminal_total = runs_completed + runs_failed + runs_interrupted
        error_rate = (runs_failed / terminal_total) if terminal_total else 0.0

        async with self._db.execute(
            "SELECT started_at, ended_at FROM runs WHERE status IN ('completed','failed','interrupted') "
            "AND started_at IS NOT NULL AND ended_at IS NOT NULL"
        ) as cur:
            timing_rows = await cur.fetchall()

        durations_ms: List[float] = []
        for tr in timing_rows:
            start = self._iso_to_epoch(tr["started_at"])
            end = self._iso_to_epoch(tr["ended_at"])
            if start is not None and end is not None:
                durations_ms.append(max(0.0, (end - start) * 1000.0))

        avg_latency_ms = (sum(durations_ms) / len(durations_ms)) if durations_ms else 0.0
        p95_latency_ms = 0.0
        if durations_ms:
            durations_ms.sort()
            idx = max(0, int((len(durations_ms) - 1) * 0.95))
            p95_latency_ms = durations_ms[idx]

        async with self._db.execute("SELECT SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) FROM approvals") as cur:
            pending_approvals = (await cur.fetchone())[0] or 0

        return {
            "sessions": session_count,
            "queue_depth": queue_depth,
            "pending_approvals": pending_approvals,
            "runs_total": runs_total,
            "runs_active": runs_active,
            "runs_completed": runs_completed,
            "runs_failed": runs_failed,
            "runs_interrupted": runs_interrupted,
            "error_rate": round(error_rate, 6),
            "avg_latency_ms": round(avg_latency_ms, 3),
            "p95_latency_ms": round(p95_latency_ms, 3),
            "total_tokens": total_tokens,
            "total_estimated_cost_usd": round(total_cost, 8),
        }

    async def get_alerts(self) -> List[Dict[str, Any]]:
        metrics = await self.get_runtime_metrics()
        checks = [
            ("error_rate", metrics["error_rate"], float(self.alert_thresholds.get("max_error_rate", 0.2))),
            ("p95_latency_ms", metrics["p95_latency_ms"], float(self.alert_thresholds.get("max_p95_latency_ms", 0.0))),
            (
                "total_estimated_cost_usd",
                metrics["total_estimated_cost_usd"],
                float(self.alert_thresholds.get("max_total_cost_usd", 0.0)),
            ),
            ("queue_depth", float(metrics["queue_depth"]), float(self.alert_thresholds.get("max_queue_depth", 0.0))),
        ]
        alerts: List[Dict[str, Any]] = []
        for name, value, threshold in checks:
            st = "alert" if value > threshold else "ok"
            msg = (
                f"{name}={value} exceeds threshold={threshold}"
                if st == "alert"
                else f"{name}={value} within threshold={threshold}"
            )
            alerts.append(
                {"name": name, "status": st, "value": float(value), "threshold": float(threshold), "message": msg}
            )
        return alerts

    def get_provider_policy(self) -> Dict[str, Any]:
        return self.provider_error_policy

    def runtime_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "retry_max_attempts": str(self.provider_error_policy.get("retry", {}).get("max_attempts", 0)),
            "fallback_chain_size": str(len(self.provider_error_policy.get("fallback_chain", []))),
        }

    # PLACEHOLDER_EVENTS

    # -- events / streaming --------------------------------------------------

    async def snapshot_events(
        self, session_id: str, run_id: str, tenant_id: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], str]:
        run = await self.get_run(session_id, run_id, tenant_id=tenant_id)
        return list(run.events), run.status

    async def event_index_after(
        self,
        session_id: str,
        run_id: str,
        last_event_id: Optional[str],
        tenant_id: Optional[str] = None,
    ) -> int:
        if not last_event_id:
            return 0
        run = await self.get_run(session_id, run_id, tenant_id=tenant_id)
        for idx, event in enumerate(run.events):
            if event["event_id"] == last_event_id:
                return idx + 1
        return 0

    # -- approvals -----------------------------------------------------------

    async def list_pending_approvals(self, session_id: str, tenant_id: Optional[str] = None) -> List[ApprovalRecord]:
        await self.get_session(session_id, tenant_id=tenant_id)
        async with self._db.execute(
            "SELECT * FROM approvals WHERE session_id = ? AND status = 'pending' ORDER BY created_at",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_approval(r) for r in rows]

    async def approve_approval(
        self,
        session_id: str,
        approval_id: str,
        apply_to_future: bool,
        tenant_id: Optional[str] = None,
    ) -> ApprovalRecord:
        await self.get_session(session_id, tenant_id=tenant_id)

        async with self._db.execute(
            "SELECT * FROM approvals WHERE approval_id = ? AND session_id = ?",
            (approval_id, session_id),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise APIError(404, "APPROVAL_NOT_FOUND", f"Approval '{approval_id}' not found")
        if row["status"] != "pending":
            raise APIError(409, "APPROVAL_ALREADY_PROCESSED", "Approval is already processed")

        run = await self.get_run(session_id, row["run_id"])
        if run.status != "waiting_approval" or run.pending_approval_id != approval_id:
            raise APIError(409, "INVALID_STATE", "Approval is not active for this run")

        now = utc_now_iso()
        await self._db.execute(
            "UPDATE approvals SET status = 'approved', decided_at = ? WHERE approval_id = ?",
            (now, approval_id),
        )
        await self._db.execute(
            "UPDATE runs SET pending_approval_id = NULL WHERE run_id = ?",
            (run.run_id,),
        )
        run.pending_approval_id = None

        # Decrement pending count
        await self._db.execute(
            "UPDATE sessions SET pending_approvals_count = MAX(0, pending_approvals_count - 1) WHERE session_id = ?",
            (session_id,),
        )
        if apply_to_future:
            session = await self.get_session(session_id)
            session.settings["auto_approve"] = True
            await self._db.execute(
                "UPDATE sessions SET settings_json = ? WHERE session_id = ?",
                (json.dumps(session.settings), session_id),
            )
        await self._db.commit()

        await self._append_event(session_id, run.run_id, "tool_call_approved", {"approval_id": approval_id})
        run.wait_event.set()
        await self._audit(
            action="approval_decided",
            session_id=session_id,
            run_id=run.run_id,
            details={"approval_id": approval_id, "decision": "approved", "apply_to_future": apply_to_future},
        )

        approval = _row_to_approval(row)
        approval.status = "approved"
        approval.decided_at = now
        return approval

    # PLACEHOLDER_REJECT

    async def reject_approval(
        self, session_id: str, approval_id: str, tenant_id: Optional[str] = None
    ) -> ApprovalRecord:
        await self.get_session(session_id, tenant_id=tenant_id)

        async with self._db.execute(
            "SELECT * FROM approvals WHERE approval_id = ? AND session_id = ?",
            (approval_id, session_id),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise APIError(404, "APPROVAL_NOT_FOUND", f"Approval '{approval_id}' not found")
        if row["status"] != "pending":
            raise APIError(409, "APPROVAL_ALREADY_PROCESSED", "Approval is already processed")

        run = await self.get_run(session_id, row["run_id"])
        if run.status != "waiting_approval" or run.pending_approval_id != approval_id:
            raise APIError(409, "INVALID_STATE", "Approval is not active for this run")

        now = utc_now_iso()
        await self._db.execute(
            "UPDATE approvals SET status = 'rejected', decided_at = ? WHERE approval_id = ?",
            (now, approval_id),
        )
        await self._db.execute(
            "UPDATE runs SET pending_approval_id = NULL WHERE run_id = ?",
            (run.run_id,),
        )
        run.pending_approval_id = None
        await self._db.execute(
            "UPDATE sessions SET pending_approvals_count = MAX(0, pending_approvals_count - 1) WHERE session_id = ?",
            (session_id,),
        )
        await self._db.commit()

        await self._append_event(
            session_id, run.run_id, "tool_call_rejected", {"approval_id": approval_id, "reason": "user_rejected"}
        )
        run.wait_event.set()
        await self._audit(
            action="approval_decided",
            session_id=session_id,
            run_id=run.run_id,
            details={"approval_id": approval_id, "decision": "rejected"},
        )

        approval = _row_to_approval(row)
        approval.status = "rejected"
        approval.decided_at = now
        return approval

    # -- files ---------------------------------------------------------------

    async def upload_session_file(
        self,
        session_id: str,
        filename: str,
        content: bytes,
        mime_type: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> WorkspaceFile:
        await self.get_session(session_id, tenant_id=tenant_id)
        self._validate_upload(content=content, mime_type=mime_type)
        saved = await self._workspace_provider.save_uploaded_file(
            session_id=session_id,
            filename=filename,
            content=content,
        )
        await self._audit(
            action="file_uploaded",
            session_id=session_id,
            details={"path": saved.path, "size": saved.size, "mime_type": saved.mime_type},
        )
        return saved

    async def list_session_files(self, session_id: str, tenant_id: Optional[str] = None) -> List[WorkspaceFile]:
        await self.get_session(session_id, tenant_id=tenant_id)
        workspace_files = await self._workspace_provider.list_files(session_id=session_id)
        if not self._artifact_storage_provider:
            return workspace_files
        artifacts = await self._artifact_storage_provider.list_artifacts(session_id=session_id)
        merged: Dict[str, WorkspaceFile] = {item.path: item for item in workspace_files}
        for item in artifacts:
            merged[item.path] = item
        return [merged[path] for path in sorted(merged.keys())]

    async def read_session_file(
        self, session_id: str, file_path: str, tenant_id: Optional[str] = None
    ) -> WorkspaceFileContent:
        await self.get_session(session_id, tenant_id=tenant_id)
        try:
            return await self._workspace_provider.read_file(session_id=session_id, relative_path=file_path)
        except APIError as exc:
            if exc.code != "FILE_NOT_FOUND" or not self._artifact_storage_provider:
                raise
            return await self._artifact_storage_provider.read_artifact(session_id=session_id, artifact_path=file_path)

    # PLACEHOLDER_PRIVATE

    # -- private helpers -----------------------------------------------------

    async def _audit(
        self,
        action: str,
        session_id: str,
        run_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            session = await self.get_session(session_id)
            tenant_id = session.tenant_id
        except APIError:
            tenant_id = "-"
        safe_details = redact_for_log(details or {})
        audit_logger.info(
            "audit action=%s tenant_id=%s session_id=%s run_id=%s details=%s",
            action,
            tenant_id,
            session_id,
            run_id or "-",
            safe_details,
        )

    def _validate_upload(self, content: bytes, mime_type: Optional[str]) -> None:
        if len(content) > self.max_upload_bytes:
            raise APIError(
                422, "UPLOAD_TOO_LARGE", "Uploaded file exceeds size limit", {"max_upload_bytes": self.max_upload_bytes}
            )
        normalized = (mime_type or "").strip().lower()
        if normalized and normalized not in self.allowed_upload_mime_types:
            raise APIError(
                422,
                "UNSUPPORTED_FILE_TYPE",
                "Uploaded file type is not allowed",
                {"mime_type": normalized, "allowed": sorted(self.allowed_upload_mime_types)},
            )

    async def _promote_workflow(self, session_id: str, state: str) -> None:
        async with self._db.execute(
            "SELECT workflow_state FROM sessions WHERE session_id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return
        current = WORKFLOW_ORDER.get(row["workflow_state"], -1)
        target = WORKFLOW_ORDER.get(state)
        if target is not None and target >= current:
            await self._db.execute(
                "UPDATE sessions SET workflow_state = ? WHERE session_id = ?",
                (state, session_id),
            )

    async def _set_run_status(
        self,
        session_id: str,
        run_id: str,
        status: str,
        error: Optional[Dict[str, Any]] = None,
    ) -> None:
        run = await self.get_run(session_id, run_id)
        run.status = status
        if status == "running" and not run.started_at:
            run.started_at = utc_now_iso()
        if status in TERMINAL_RUN_STATES:
            run.ended_at = utc_now_iso()
            run.error = error
            if not run.usage_finalized:
                self._finalize_run_usage(run)
            run.pending_approval_id = None
            # Clean up any pending approvals for this run
            await self._db.execute(
                "UPDATE approvals SET status = 'rejected', decided_at = ? " "WHERE run_id = ? AND status = 'pending'",
                (utc_now_iso(), run_id),
            )
            # Clear active_run_id on session
            await self._db.execute(
                "UPDATE sessions SET active_run_id = NULL WHERE session_id = ? AND active_run_id = ?",
                (session_id, run_id),
            )
            # Remove from in-memory active runs
            async with self._lock:
                self._active_runs.pop(run_id, None)

        await self._db.execute(
            "UPDATE runs SET status = ?, started_at = ?, ended_at = ?, error_json = ?, "
            "pending_approval_id = ?, usage_tokens = ?, estimated_cost_usd = ?, usage_finalized = ? "
            "WHERE run_id = ?",
            (
                run.status,
                run.started_at,
                run.ended_at,
                json.dumps(run.error) if run.error else None,
                run.pending_approval_id,
                run.usage_tokens,
                run.estimated_cost_usd,
                int(run.usage_finalized),
                run_id,
            ),
        )
        await self._db.commit()

    async def _append_event(
        self,
        session_id: str,
        run_id: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> None:
        run = await self.get_run(session_id, run_id)
        run.event_seq += 1
        event_id = f"evt_{run_id}_{run.event_seq:04d}"
        event = {
            "event_id": event_id,
            "session_id": session_id,
            "run_id": run_id,
            "type": event_type,
            "ts": utc_now_iso(),
            "payload": payload,
        }
        run.events.append(event)
        await self._db.execute(
            "UPDATE runs SET events_json = ?, event_seq = ? WHERE run_id = ?",
            (json.dumps(run.events), run.event_seq, run_id),
        )
        await self._db.commit()

    # PLACEHOLDER_WORKER

    def _finalize_run_usage(self, run: RunRecord) -> None:
        text_size = len(run.message or "")
        for event in run.events:
            text_size += len(event.get("type", ""))
            text_size += len(str(event.get("payload", {})))
        estimated_tokens = max(text_size // 4, 1)
        estimated_cost = (estimated_tokens / 1_000_000) * self.cost_per_million_tokens
        run.usage_tokens = estimated_tokens
        run.estimated_cost_usd = round(estimated_cost, 8)
        run.usage_finalized = True

    def _get_or_create_agent(self, session: SessionRecord) -> Any:
        if session._agent is not None:
            return session._agent
        if not self._llm_config:
            raise APIError(500, "INTERNAL_ERROR", "LLM config not initialized for real mode")
        from packages.core.resume_agent_core import AgentConfig, ResumeAgent

        workspace_dir = str(self._workspace_provider.root_dir / session.session_id)
        agent = ResumeAgent(llm_config=self._llm_config, agent_config=AgentConfig(workspace_dir=workspace_dir))
        if session.settings.get("auto_approve"):
            agent.agent.set_auto_approve_tools(True)
        session._agent = agent
        return agent

    async def _restore_agent_history(self, session_id: str, agent: Any) -> None:
        """Restore conversation history from DB into agent."""
        async with self._db.execute(
            "SELECT conversation_json FROM sessions WHERE session_id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row and row["conversation_json"]:
            from packages.core.resume_agent_core.session import SessionSerializer

            messages = SessionSerializer.deserialize_history(json.loads(row["conversation_json"]))
            agent.agent.history_manager._history = messages

    async def _save_agent_history(self, session_id: str, agent: Any) -> None:
        """Persist agent conversation history to DB."""
        from packages.core.resume_agent_core.session import SessionSerializer

        history_data = SessionSerializer.serialize_history(agent.agent.history_manager)
        await self._db.execute(
            "UPDATE sessions SET conversation_json = ? WHERE session_id = ?",
            (json.dumps(history_data), session_id),
        )
        await self._db.commit()

    # -- run worker ----------------------------------------------------------

    async def _run_worker(self) -> None:
        while not self._stop_requested:
            session_id, run_id = await self._run_queue.get()
            if session_id is None or run_id is None:
                self._run_queue.task_done()
                break
            if self._executor_mode == "real":
                await self._execute_real_run(session_id=session_id, run_id=run_id)
            else:
                await self._execute_stub_run(session_id=session_id, run_id=run_id)
            self._run_queue.task_done()

    # PLACEHOLDER_REAL_RUN

    async def _execute_real_run(self, session_id: str, run_id: str) -> None:
        try:
            await self._set_run_status(session_id, run_id, "running")
            await self._append_event(session_id, run_id, "run_started", {"status": "running"})

            session = await self.get_session(session_id)
            agent = self._get_or_create_agent(session)
            await self._restore_agent_history(session_id, agent)
            message = (await self.get_run(session_id, run_id)).message

            async def on_stream_delta(delta):
                if delta.text:
                    await self._append_event(session_id, run_id, "assistant_delta", {"text": delta.text})

            async def approval_handler(function_calls):
                approvals = []
                for fc in function_calls:
                    target_path = fc.arguments.get("path", "unknown") if fc.arguments else "unknown"
                    approval = await self._create_approval(
                        session_id,
                        run_id,
                        target_path,
                        tool_name=fc.name,
                        args=dict(fc.arguments) if fc.arguments else {},
                    )
                    approvals.append(approval)
                    await self._append_event(
                        session_id,
                        run_id,
                        "tool_call_proposed",
                        {
                            "approval_id": approval.approval_id,
                            "tool_name": approval.tool_name,
                            "args": approval.args,
                        },
                    )
                await self._set_run_status(session_id, run_id, "waiting_approval")
                await self._wait_until_approval_or_interrupt(session_id, run_id)
                run = await self.get_run(session_id, run_id)
                if run.interrupt_requested:
                    return [], "interrupted"
                approved_calls = []
                for approval in approvals:
                    status = await self._get_approval_status(session_id, approval.approval_id)
                    if status == "rejected":
                        return [], "user_rejected"
                    approved_calls.append(
                        type(
                            "FunctionCall",
                            (),
                            {"name": approval.tool_name, "arguments": approval.args, "id": approval.approval_id},
                        )()
                    )
                await self._set_run_status(session_id, run_id, "running")
                return approved_calls, None

            async def tool_event_handler(event_type, tool_name, args, result, success):
                if event_type == "tool_end":
                    await self._append_event(
                        session_id,
                        run_id,
                        "tool_result",
                        {
                            "tool_name": tool_name,
                            "success": success,
                            "result": result or "",
                        },
                    )

            async def interrupt_checker():
                run = await self.get_run(session_id, run_id)
                return run.interrupt_requested

            agent.agent.set_approval_handler(approval_handler)
            agent.agent.set_tool_event_handler(tool_event_handler)
            agent.agent.set_interrupt_checker(interrupt_checker)

            try:
                final_text = await agent.run(message, stream=True, on_stream_delta=on_stream_delta)
                if hasattr(agent.agent, "observer") and hasattr(agent.agent.observer, "total_tokens"):
                    run = await self.get_run(session_id, run_id)
                    run.usage_tokens = agent.agent.observer.total_tokens
                    run.estimated_cost_usd = agent.agent.observer.total_cost
                await self._append_event(
                    session_id, run_id, "run_completed", {"status": "completed", "final_text": final_text}
                )
                await self._set_run_status(session_id, run_id, "completed")
            except asyncio.CancelledError:
                await self._append_event(session_id, run_id, "run_interrupted", {"status": "interrupted"})
                await self._set_run_status(session_id, run_id, "interrupted")
            finally:
                agent.agent.set_approval_handler(None)
                agent.agent.set_tool_event_handler(None)
                agent.agent.set_interrupt_checker(None)
                await self._save_agent_history(session_id, agent)

        except Exception as exc:
            await self._append_event(
                session_id,
                run_id,
                "run_failed",
                {
                    "status": "failed",
                    "error_code": "INTERNAL_ERROR",
                    "message": str(exc),
                },
            )
            await self._set_run_status(
                session_id, run_id, "failed", error={"code": "INTERNAL_ERROR", "message": str(exc)}
            )

    # PLACEHOLDER_STUB_RUN

    async def _execute_stub_run(self, session_id: str, run_id: str) -> None:
        try:
            await self._set_run_status(session_id, run_id, "running")
            await self._append_event(session_id, run_id, "run_started", {"status": "running"})
            if await self._finalize_interrupt_if_requested(session_id, run_id):
                return

            await self._append_event(
                session_id, run_id, "assistant_delta", {"text": "Stub executor: request accepted and being processed."}
            )

            message = (await self.get_run(session_id, run_id)).message
            normalized_message = message.lower()
            if "long" in normalized_message:
                if not await self._sleep_with_interrupt(session_id, run_id, 1.0):
                    return
            else:
                if not await self._sleep_with_interrupt(session_id, run_id, 0.05):
                    return

            if "gap" in normalized_message or "analy" in normalized_message:
                await self._promote_workflow(session_id, "gap_analyzed")

            if self._message_requires_write(message):
                target_path = self._extract_target_path(message)
                auto_approve = (await self.get_session(session_id)).settings.get("auto_approve", False)
                if auto_approve:
                    await self._apply_stub_file_write(session_id, target_path, message, run_id)
                    await self._promote_workflow(session_id, "rewrite_applied")
                    await self._append_event(
                        session_id,
                        run_id,
                        "tool_result",
                        {
                            "tool_name": "file_write",
                            "success": True,
                            "result": f"Stub wrote content to {target_path}",
                        },
                    )
                else:
                    approval = await self._create_approval(session_id, run_id, target_path)
                    await self._append_event(
                        session_id,
                        run_id,
                        "tool_call_proposed",
                        {
                            "approval_id": approval.approval_id,
                            "tool_name": approval.tool_name,
                            "args": approval.args,
                        },
                    )
                    await self._set_run_status(session_id, run_id, "waiting_approval")
                    await self._wait_until_approval_or_interrupt(session_id, run_id)
                    if await self._finalize_interrupt_if_requested(session_id, run_id):
                        return
                    approval_state = await self._get_approval_status(session_id, approval.approval_id)
                    if approval_state == "rejected":
                        await self._append_event(
                            session_id,
                            run_id,
                            "run_completed",
                            {
                                "status": "completed",
                                "final_text": "Run completed without write changes (rejected).",
                            },
                        )
                        await self._set_run_status(session_id, run_id, "completed")
                        return
                    await self._set_run_status(session_id, run_id, "running")
                    await self._apply_stub_file_write(session_id, target_path, message, run_id)
                    await self._promote_workflow(session_id, "rewrite_applied")
                    await self._append_event(
                        session_id,
                        run_id,
                        "tool_result",
                        {
                            "tool_name": "file_write",
                            "success": True,
                            "result": f"Stub wrote content to {target_path}",
                        },
                    )

            if not await self._sleep_with_interrupt(session_id, run_id, 0.05):
                return

            await self._append_event(
                session_id, run_id, "run_completed", {"status": "completed", "final_text": "Stub run completed."}
            )
            await self._set_run_status(session_id, run_id, "completed")
        except Exception as exc:
            await self._append_event(
                session_id,
                run_id,
                "run_failed",
                {
                    "status": "failed",
                    "error_code": "INTERNAL_ERROR",
                    "message": str(exc),
                },
            )
            await self._set_run_status(
                session_id, run_id, "failed", error={"code": "INTERNAL_ERROR", "message": str(exc)}
            )

    # PLACEHOLDER_APPROVAL_HELPERS

    async def _create_approval(
        self,
        session_id: str,
        run_id: str,
        target_path: str,
        tool_name: str = "file_write",
        args: Optional[Dict[str, Any]] = None,
    ) -> ApprovalRecord:
        approval_id = make_id("appr")
        now = utc_now_iso()
        final_args = args or {"path": target_path}
        approval = ApprovalRecord(
            approval_id=approval_id,
            session_id=session_id,
            run_id=run_id,
            tool_name=tool_name,
            args=final_args,
            created_at=now,
        )
        await self._db.execute(
            "INSERT INTO approvals (approval_id, session_id, run_id, tool_name, args_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (approval_id, session_id, run_id, tool_name, json.dumps(final_args), now),
        )
        await self._db.execute(
            "UPDATE sessions SET pending_approvals_count = pending_approvals_count + 1 WHERE session_id = ?",
            (session_id,),
        )
        # Update run's pending_approval_id
        run = await self.get_run(session_id, run_id)
        run.pending_approval_id = approval_id
        run.wait_event.clear()
        await self._db.execute(
            "UPDATE runs SET pending_approval_id = ? WHERE run_id = ?",
            (approval_id, run_id),
        )
        await self._db.commit()
        return approval

    async def _get_approval_status(self, session_id: str, approval_id: str) -> str:
        async with self._db.execute(
            "SELECT status FROM approvals WHERE approval_id = ? AND session_id = ?",
            (approval_id, session_id),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise APIError(404, "APPROVAL_NOT_FOUND", f"Approval '{approval_id}' not found")
        return row["status"]

    async def _wait_until_approval_or_interrupt(self, session_id: str, run_id: str) -> None:
        while True:
            run = await self.get_run(session_id, run_id)
            if run.interrupt_requested or run.pending_approval_id is None:
                return
            await run.wait_event.wait()
            run.wait_event.clear()

    async def _finalize_interrupt_if_requested(self, session_id: str, run_id: str) -> bool:
        run = await self.get_run(session_id, run_id)
        if not run.interrupt_requested:
            return False
        if run.status in TERMINAL_RUN_STATES:
            return True
        await self._append_event(session_id, run_id, "run_interrupted", {"status": "interrupted"})
        await self._set_run_status(session_id, run_id, "interrupted")
        return True

    async def _sleep_with_interrupt(self, session_id: str, run_id: str, seconds: float) -> bool:
        remaining = seconds
        slice_seconds = 0.05
        while remaining > 0:
            if await self._finalize_interrupt_if_requested(session_id, run_id):
                return False
            await asyncio.sleep(min(slice_seconds, remaining))
            remaining -= slice_seconds
        return not await self._finalize_interrupt_if_requested(session_id, run_id)

    async def _apply_stub_file_write(
        self,
        session_id: str,
        target_path: str,
        message: str,
        run_id: str,
    ) -> WorkspaceFile:
        normalized_path = Path(target_path).as_posix()
        content_hint = f"Updated by run {run_id}: {message.strip()}"
        try:
            existing = await self.read_session_file(session_id=session_id, file_path=normalized_path)
            try:
                base_text = existing.content.decode("utf-8")
            except UnicodeDecodeError:
                base_text = ""
            if base_text and not base_text.endswith("\n"):
                base_text += "\n"
            next_text = f"{base_text}\n- {content_hint}\n"
        except APIError as exc:
            if exc.code != "FILE_NOT_FOUND":
                raise
            next_text = f"# Resume Draft\n\n- {content_hint}\n"

        written = await self._workspace_provider.write_file(
            session_id=session_id,
            relative_path=normalized_path,
            content=next_text.encode("utf-8"),
        )

        # Update resume_path if applicable
        session = await self.get_session(session_id)
        if session.resume_path is None or session.resume_path == normalized_path:
            await self._db.execute(
                "UPDATE sessions SET resume_path = ? WHERE session_id = ?",
                (normalized_path, session_id),
            )
            await self._db.commit()

        await self._audit(
            action="file_written",
            session_id=session_id,
            run_id=run_id,
            details={"path": normalized_path, "bytes": written.size, "message_preview": message},
        )
        return written

    # PLACEHOLDER_NORMALIZE

    # -- startup normalization -----------------------------------------------

    async def _normalize_active_runs(self) -> None:
        """Mark any active runs as interrupted on startup (can't resume across restarts)."""
        now = utc_now_iso()
        active_statuses = tuple(ACTIVE_RUN_STATES)
        placeholders = ",".join("?" for _ in active_statuses)

        async with self._db.execute(
            f"SELECT run_id, session_id, events_json, event_seq FROM runs WHERE status IN ({placeholders})",
            active_statuses,
        ) as cursor:
            rows = await cursor.fetchall()

        for row in rows:
            run_id = row["run_id"]
            session_id = row["session_id"]
            events = json.loads(row["events_json"]) if row["events_json"] else []
            event_seq = row["event_seq"] or len(events)

            if not any(e.get("type") == "run_interrupted" for e in events):
                event_seq += 1
                events.append(
                    {
                        "event_id": f"evt_{run_id}_{event_seq:04d}",
                        "session_id": session_id,
                        "run_id": run_id,
                        "type": "run_interrupted",
                        "ts": now,
                        "payload": {"status": "interrupted", "reason": "process_restarted"},
                    }
                )

            await self._db.execute(
                "UPDATE runs SET status = 'interrupted', interrupt_requested = 1, "
                "ended_at = COALESCE(ended_at, ?), started_at = COALESCE(started_at, created_at), "
                "events_json = ?, event_seq = ?, pending_approval_id = NULL "
                "WHERE run_id = ?",
                (now, json.dumps(events), event_seq, run_id),
            )

        # Collect affected run_ids for subsequent cleanup
        affected_run_ids = [row["run_id"] for row in rows]

        if affected_run_ids:
            run_placeholders = ",".join("?" for _ in affected_run_ids)

            # Reject orphaned pending approvals
            await self._db.execute(
                "UPDATE approvals SET status = 'rejected', decided_at = ? "
                f"WHERE status = 'pending' AND run_id IN ({run_placeholders})",
                (now, *affected_run_ids),
            )

            # Clear active_run_id on sessions whose active run was just interrupted
            await self._db.execute(
                "UPDATE sessions SET active_run_id = NULL "
                f"WHERE active_run_id IS NOT NULL AND active_run_id IN ({run_placeholders})",
                affected_run_ids,
            )

        # Recount pending approvals
        await self._db.execute(
            "UPDATE sessions SET pending_approvals_count = ("
            "  SELECT COUNT(*) FROM approvals WHERE approvals.session_id = sessions.session_id AND approvals.status = 'pending'"
            ")"
        )

        await self._db.commit()

    # -- cleanup -------------------------------------------------------------

    async def cleanup_expired_resources(self) -> Dict[str, int]:
        removed_sessions: List[str] = []

        if self.session_ttl_seconds > 0:
            now_epoch = datetime.now(timezone.utc).timestamp()
            async with self._db.execute("SELECT session_id, created_at, active_run_id FROM sessions") as cursor:
                rows = await cursor.fetchall()

            for row in rows:
                if row["active_run_id"]:
                    continue
                try:
                    created_epoch = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")).timestamp()
                except ValueError:
                    continue
                if now_epoch - created_epoch >= self.session_ttl_seconds:
                    removed_sessions.append(row["session_id"])

            for sid in removed_sessions:
                await self._db.execute("DELETE FROM approvals WHERE session_id = ?", (sid,))
                await self._db.execute("DELETE FROM runs WHERE session_id = ?", (sid,))
                await self._db.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))
            if removed_sessions:
                await self._db.commit()

        removed_workspace_files = 0
        removed_artifact_files = 0
        for sid in removed_sessions:
            removed_workspace_files += await self._workspace_provider.delete_workspace(session_id=sid)
            if self._artifact_storage_provider:
                removed_artifact_files += await self._artifact_storage_provider.delete_artifacts_for_session(
                    session_id=sid
                )

        if self.artifact_ttl_seconds > 0 and self._artifact_storage_provider:
            removed_artifact_files += await self._artifact_storage_provider.cleanup_expired(
                ttl_seconds=self.artifact_ttl_seconds
            )

        return {
            "removed_sessions": len(removed_sessions),
            "removed_workspace_files": removed_workspace_files,
            "removed_artifact_files": removed_artifact_files,
        }

    async def _cleanup_worker(self) -> None:
        while not self._stop_requested:
            await asyncio.sleep(self.cleanup_interval_seconds)
            if self._stop_requested:
                break
            await self.cleanup_expired_resources()

    # -- static helpers (same as InMemoryRuntimeStore) -----------------------

    @staticmethod
    def _build_export_content(source: bytes) -> bytes:
        try:
            text = source.decode("utf-8")
        except UnicodeDecodeError:
            text = source.decode("utf-8", errors="replace")
        header = "# Exported Resume\n\nGenerated by Resume Agent Web UI.\n\n---\n\n"
        return f"{header}{text}".encode("utf-8")

    @staticmethod
    def _iso_to_epoch(value: str) -> Optional[float]:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None

    @staticmethod
    def _message_requires_write(message: str) -> bool:
        normalized = message.lower()
        return any(keyword in normalized for keyword in WRITE_INTENT_KEYWORDS)

    @staticmethod
    def _extract_target_path(message: str) -> str:
        match = re.search(r"([\w./-]+\.[a-zA-Z0-9]{1,8})", message)
        if match:
            return match.group(1)
        return "resume.md"
