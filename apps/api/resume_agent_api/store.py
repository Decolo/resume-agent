"""In-memory runtime store for Web API v1."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
from .workspace import WorkspaceFile, WorkspaceFileContent, WorkspaceProvider

WRITE_INTENT_KEYWORDS = ("write", "update", "modify", "edit", "create", "copy")
STATE_SCHEMA_VERSION = 1
logger = logging.getLogger("resume_agent.web.api")
audit_logger = logging.getLogger("resume_agent.web.audit")


def utc_now_iso() -> str:
    """Return current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_id(prefix: str) -> str:
    """Create opaque id matching the documented prefix style."""
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@dataclass
class ApprovalRecord:
    approval_id: str
    session_id: str
    run_id: str
    tool_name: str
    args: Dict[str, Any]
    created_at: str
    status: str = "pending"
    decided_at: Optional[str] = None


@dataclass
class RunRecord:
    run_id: str
    session_id: str
    message: str
    status: str
    created_at: str
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    error: Optional[Dict[str, Any]] = None
    events: List[Dict[str, Any]] = field(default_factory=list)
    event_seq: int = 0
    interrupt_requested: bool = False
    pending_approval_id: Optional[str] = None
    usage_tokens: int = 0
    estimated_cost_usd: float = 0.0
    usage_finalized: bool = False
    wait_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_RUN_STATES


@dataclass
class SessionRecord:
    session_id: str
    tenant_id: str
    workspace_name: str
    created_at: str
    workflow_state: str
    settings: Dict[str, Any]
    active_run_id: Optional[str] = None
    pending_approvals_count: int = 0
    resume_path: Optional[str] = None
    jd_text: Optional[str] = None
    jd_url: Optional[str] = None
    latest_export_path: Optional[str] = None
    runs: Dict[str, RunRecord] = field(default_factory=dict)
    approvals: Dict[str, ApprovalRecord] = field(default_factory=dict)
    idempotency_keys: Dict[str, Tuple[str, str]] = field(default_factory=dict)


class InMemoryRuntimeStore:
    """Runtime persistence + deterministic stub executor for web contract tests."""

    def __init__(
        self,
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
        state_file: Optional[Path] = None,
        alert_thresholds: Optional[Dict[str, float]] = None,
    ) -> None:
        self._sessions: Dict[str, SessionRecord] = {}
        self._lock = asyncio.Lock()
        self._persist_lock = asyncio.Lock()
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
        self.allowed_upload_mime_types = set(allowed_upload_mime_types or DEFAULT_ALLOWED_UPLOAD_MIME_TYPES)
        self.cost_per_million_tokens = max(cost_per_million_tokens, 0.0)
        self.session_ttl_seconds = max(session_ttl_seconds, 0)
        self.artifact_ttl_seconds = max(artifact_ttl_seconds, 0)
        self.cleanup_interval_seconds = max(cleanup_interval_seconds, 1)
        self.provider_error_policy = provider_error_policy or {
            "retry": {"max_attempts": 3, "base_delay_seconds": 1.0, "max_delay_seconds": 30.0},
            "fallback_chain": [],
        }
        self.state_file = state_file.resolve() if state_file else None
        self.alert_thresholds = alert_thresholds or {
            "max_error_rate": 0.2,
            "max_p95_latency_ms": 15_000.0,
            "max_total_cost_usd": 10.0,
            "max_queue_depth": 50.0,
        }

    async def start(self) -> None:
        """Start background run worker."""
        await self._load_state()
        if self._worker_task is None:
            self._stop_requested = False
            self._worker_task = asyncio.create_task(self._run_worker())
        if self._cleanup_task is None and (self.session_ttl_seconds > 0 or self.artifact_ttl_seconds > 0):
            self._cleanup_task = asyncio.create_task(self._cleanup_worker())

    async def stop(self) -> None:
        """Stop background run worker."""
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
        await self._persist_state()

    async def create_session(self, workspace_name: str, auto_approve: bool, tenant_id: str) -> SessionRecord:
        session_id = make_id("sess")
        await self._workspace_provider.create_workspace(session_id=session_id, workspace_name=workspace_name)
        session = SessionRecord(
            session_id=session_id,
            tenant_id=tenant_id,
            workspace_name=workspace_name,
            created_at=utc_now_iso(),
            workflow_state="draft",
            settings={"auto_approve": auto_approve},
        )
        async with self._lock:
            self._sessions[session_id] = session
        await self._persist_state()
        return session

    def runtime_metadata(self) -> Dict[str, str]:
        """Static provider/model values used by API observability logs."""
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "retry_max_attempts": str(self.provider_error_policy.get("retry", {}).get("max_attempts", 0)),
            "fallback_chain_size": str(len(self.provider_error_policy.get("fallback_chain", []))),
        }

    async def _audit(
        self,
        action: str,
        session_id: str,
        run_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            tenant_id = session.tenant_id if session else "-"
        safe_details = redact_for_log(details or {})
        audit_logger.info(
            "audit action=%s tenant_id=%s session_id=%s run_id=%s details=%s",
            action,
            tenant_id,
            session_id,
            run_id or "-",
            safe_details,
        )

    async def get_session(self, session_id: str, tenant_id: Optional[str] = None) -> SessionRecord:
        async with self._lock:
            session = self._session_for_tenant_locked(session_id=session_id, tenant_id=tenant_id)
        return session

    async def set_auto_approve(
        self,
        session_id: str,
        enabled: bool,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, bool]:
        async with self._lock:
            session = self._session_for_tenant_locked(session_id=session_id, tenant_id=tenant_id)
            session.settings["auto_approve"] = enabled
        await self._persist_state()
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
        async with self._lock:
            session = self._session_for_tenant_locked(session_id=session_id, tenant_id=tenant_id)
            session.resume_path = metadata.path
            self._promote_workflow_locked(session, "resume_uploaded")
        await self._persist_state()
        return metadata

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

        async with self._lock:
            session = self._session_for_tenant_locked(session_id=session_id, tenant_id=tenant_id)
            if not session.resume_path:
                raise APIError(
                    409,
                    "INVALID_STATE",
                    "Resume must be uploaded before submitting JD",
                )
            session.jd_text = normalized_text or None
            session.jd_url = normalized_url or None
            self._promote_workflow_locked(session, "jd_provided")
            response = {
                "workflow_state": session.workflow_state,
                "jd_text": session.jd_text,
                "jd_url": session.jd_url,
            }
        await self._persist_state()
        return response

    async def export_session(self, session_id: str, tenant_id: Optional[str] = None) -> WorkspaceFile:
        session = await self.get_session(session_id=session_id, tenant_id=tenant_id)
        source_path = session.resume_path
        if not source_path:
            files = await self.list_session_files(session_id=session_id, tenant_id=tenant_id)
            if not files:
                raise APIError(409, "INVALID_STATE", "No files available to export")
            source_path = files[0].path

        source_content = await self.read_session_file(
            session_id=session_id,
            file_path=source_path,
            tenant_id=tenant_id,
        )
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

        async with self._lock:
            session_locked = self._session_for_tenant_locked(session_id=session_id, tenant_id=tenant_id)
            session_locked.latest_export_path = artifact.path
            self._promote_workflow_locked(session_locked, "exported")
        await self._persist_state()
        await self._audit(
            action="file_exported",
            session_id=session_id,
            details={"artifact_path": artifact.path, "size": artifact.size, "mime_type": artifact.mime_type},
        )
        return artifact

    async def create_run(
        self,
        session_id: str,
        message: str,
        idempotency_key: Optional[str],
        tenant_id: Optional[str] = None,
    ) -> Tuple[RunRecord, bool]:
        message_fingerprint = message.strip()

        async with self._lock:
            session = self._session_for_tenant_locked(session_id=session_id, tenant_id=tenant_id)
            if idempotency_key:
                existing = session.idempotency_keys.get(idempotency_key)
                if existing:
                    existing_fingerprint, existing_run_id = existing
                    if existing_fingerprint != message_fingerprint:
                        raise APIError(
                            409,
                            "IDEMPOTENCY_CONFLICT",
                            "Idempotency key already used with different payload",
                        )
                    existing_run = session.runs[existing_run_id]
                    return existing_run, True

            if session.active_run_id:
                active_run = session.runs.get(session.active_run_id)
                if active_run and active_run.status in ACTIVE_RUN_STATES:
                    raise APIError(
                        409,
                        "ACTIVE_RUN_EXISTS",
                        "Session already has an active run",
                        {"run_id": active_run.run_id, "status": active_run.status},
                    )

            if len(session.runs) >= self.max_runs_per_session:
                raise APIError(
                    429,
                    "SESSION_RUN_QUOTA_EXCEEDED",
                    "Per-session run quota exceeded",
                    {"limit": self.max_runs_per_session},
                )

            run_id = make_id("run")
            run = RunRecord(
                run_id=run_id,
                session_id=session_id,
                message=message,
                status="queued",
                created_at=utc_now_iso(),
            )
            session.runs[run_id] = run
            session.active_run_id = run_id
            if idempotency_key:
                session.idempotency_keys[idempotency_key] = (message_fingerprint, run_id)

        await self._run_queue.put((session_id, run_id))
        await self._persist_state()
        return run, False

    async def get_run(
        self,
        session_id: str,
        run_id: str,
        tenant_id: Optional[str] = None,
    ) -> RunRecord:
        async with self._lock:
            session = self._session_for_tenant_locked(session_id=session_id, tenant_id=tenant_id)
            run = session.runs.get(run_id)
            if not run:
                raise APIError(404, "RUN_NOT_FOUND", f"Run '{run_id}' not found")
            return run

    async def get_session_usage(
        self,
        session_id: str,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        async with self._lock:
            session = self._session_for_tenant_locked(session_id=session_id, tenant_id=tenant_id)
            runs = list(session.runs.values())

        total_tokens = sum(max(run.usage_tokens, 0) for run in runs)
        total_cost = sum(max(run.estimated_cost_usd, 0.0) for run in runs)
        completed_runs = sum(1 for run in runs if run.status in TERMINAL_RUN_STATES)
        return {
            "run_count": len(runs),
            "completed_run_count": completed_runs,
            "total_tokens": total_tokens,
            "total_estimated_cost_usd": round(total_cost, 8),
        }

    async def get_runtime_metrics(self) -> Dict[str, Any]:
        async with self._lock:
            sessions = list(self._sessions.values())
            queue_depth = self._run_queue.qsize()

        runs: List[RunRecord] = []
        pending_approvals = 0
        for session in sessions:
            runs.extend(session.runs.values())
            pending_approvals += session.pending_approvals_count

        runs_total = len(runs)
        runs_active = sum(1 for run in runs if run.status in ACTIVE_RUN_STATES)
        runs_completed = sum(1 for run in runs if run.status == "completed")
        runs_failed = sum(1 for run in runs if run.status == "failed")
        runs_interrupted = sum(1 for run in runs if run.status == "interrupted")

        terminal_runs = [run for run in runs if run.status in TERMINAL_RUN_STATES]
        error_rate = (runs_failed / len(terminal_runs)) if terminal_runs else 0.0

        durations_ms: List[float] = []
        for run in terminal_runs:
            if not run.started_at or not run.ended_at:
                continue
            start = self._iso_to_epoch(run.started_at)
            end = self._iso_to_epoch(run.ended_at)
            if start is None or end is None:
                continue
            durations_ms.append(max(0.0, (end - start) * 1000.0))

        avg_latency_ms = (sum(durations_ms) / len(durations_ms)) if durations_ms else 0.0
        p95_latency_ms = 0.0
        if durations_ms:
            durations_ms.sort()
            idx = max(0, int((len(durations_ms) - 1) * 0.95))
            p95_latency_ms = durations_ms[idx]

        total_tokens = sum(max(run.usage_tokens, 0) for run in runs)
        total_cost = sum(max(run.estimated_cost_usd, 0.0) for run in runs)

        return {
            "sessions": len(sessions),
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
            status = "alert" if value > threshold else "ok"
            message = (
                f"{name}={value} exceeds threshold={threshold}"
                if status == "alert"
                else f"{name}={value} within threshold={threshold}"
            )
            alerts.append(
                {
                    "name": name,
                    "status": status,
                    "value": float(value),
                    "threshold": float(threshold),
                    "message": message,
                }
            )
        return alerts

    def get_provider_policy(self) -> Dict[str, Any]:
        """Return effective provider retry/fallback policy."""
        return self.provider_error_policy

    async def upload_session_file(
        self,
        session_id: str,
        filename: str,
        content: bytes,
        mime_type: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> WorkspaceFile:
        await self.get_session(session_id=session_id, tenant_id=tenant_id)
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

    async def list_session_files(
        self,
        session_id: str,
        tenant_id: Optional[str] = None,
    ) -> List[WorkspaceFile]:
        await self.get_session(session_id=session_id, tenant_id=tenant_id)
        workspace_files = await self._workspace_provider.list_files(session_id=session_id)
        if not self._artifact_storage_provider:
            return workspace_files

        artifacts = await self._artifact_storage_provider.list_artifacts(session_id=session_id)
        merged: Dict[str, WorkspaceFile] = {item.path: item for item in workspace_files}
        for item in artifacts:
            merged[item.path] = item
        return [merged[path] for path in sorted(merged.keys())]

    async def read_session_file(
        self,
        session_id: str,
        file_path: str,
        tenant_id: Optional[str] = None,
    ) -> WorkspaceFileContent:
        await self.get_session(session_id=session_id, tenant_id=tenant_id)
        try:
            return await self._workspace_provider.read_file(
                session_id=session_id,
                relative_path=file_path,
            )
        except APIError as exc:
            if exc.code != "FILE_NOT_FOUND" or not self._artifact_storage_provider:
                raise
            return await self._artifact_storage_provider.read_artifact(
                session_id=session_id,
                artifact_path=file_path,
            )

    async def list_pending_approvals(
        self,
        session_id: str,
        tenant_id: Optional[str] = None,
    ) -> List[ApprovalRecord]:
        async with self._lock:
            session = self._session_for_tenant_locked(session_id=session_id, tenant_id=tenant_id)
            items = [approval for approval in session.approvals.values() if approval.status == "pending"]
        items.sort(key=lambda item: item.created_at)
        return items

    async def approve_approval(
        self,
        session_id: str,
        approval_id: str,
        apply_to_future: bool,
        tenant_id: Optional[str] = None,
    ) -> ApprovalRecord:
        async with self._lock:
            session = self._session_for_tenant_locked(session_id=session_id, tenant_id=tenant_id)

            approval = session.approvals.get(approval_id)
            if not approval:
                raise APIError(404, "APPROVAL_NOT_FOUND", f"Approval '{approval_id}' not found")
            if approval.status != "pending":
                raise APIError(409, "APPROVAL_ALREADY_PROCESSED", "Approval is already processed")

            run = session.runs.get(approval.run_id)
            if not run:
                raise APIError(409, "INVALID_STATE", "Approval is detached from run")
            if run.status != "waiting_approval" or run.pending_approval_id != approval_id:
                raise APIError(409, "INVALID_STATE", "Approval is not active for this run")

            approval.status = "approved"
            approval.decided_at = utc_now_iso()
            session.pending_approvals_count = max(0, session.pending_approvals_count - 1)
            run.pending_approval_id = None
            if apply_to_future:
                session.settings["auto_approve"] = True

        await self._append_event(
            session_id,
            run.run_id,
            "tool_call_approved",
            {"approval_id": approval_id},
        )
        run.wait_event.set()
        await self._persist_state()
        await self._audit(
            action="approval_decided",
            session_id=session_id,
            run_id=run.run_id,
            details={"approval_id": approval_id, "decision": "approved", "apply_to_future": apply_to_future},
        )
        return approval

    async def reject_approval(
        self,
        session_id: str,
        approval_id: str,
        tenant_id: Optional[str] = None,
    ) -> ApprovalRecord:
        async with self._lock:
            session = self._session_for_tenant_locked(session_id=session_id, tenant_id=tenant_id)

            approval = session.approvals.get(approval_id)
            if not approval:
                raise APIError(404, "APPROVAL_NOT_FOUND", f"Approval '{approval_id}' not found")
            if approval.status != "pending":
                raise APIError(409, "APPROVAL_ALREADY_PROCESSED", "Approval is already processed")

            run = session.runs.get(approval.run_id)
            if not run:
                raise APIError(409, "INVALID_STATE", "Approval is detached from run")
            if run.status != "waiting_approval" or run.pending_approval_id != approval_id:
                raise APIError(409, "INVALID_STATE", "Approval is not active for this run")

            approval.status = "rejected"
            approval.decided_at = utc_now_iso()
            session.pending_approvals_count = max(0, session.pending_approvals_count - 1)
            run.pending_approval_id = None

        await self._append_event(
            session_id,
            run.run_id,
            "tool_call_rejected",
            {"approval_id": approval_id, "reason": "user_rejected"},
        )
        run.wait_event.set()
        await self._persist_state()
        await self._audit(
            action="approval_decided",
            session_id=session_id,
            run_id=run.run_id,
            details={"approval_id": approval_id, "decision": "rejected"},
        )
        return approval

    async def interrupt_run(
        self,
        session_id: str,
        run_id: str,
        tenant_id: Optional[str] = None,
    ) -> RunRecord:
        async with self._lock:
            session = self._session_for_tenant_locked(session_id=session_id, tenant_id=tenant_id)

            run = session.runs.get(run_id)
            if not run:
                raise APIError(404, "RUN_NOT_FOUND", f"Run '{run_id}' not found")

            if run.status in TERMINAL_RUN_STATES:
                return run

            run.interrupt_requested = True
            run.status = "interrupting"
            run.wait_event.set()
        await self._persist_state()
        return run

    async def snapshot_events(
        self,
        session_id: str,
        run_id: str,
        tenant_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], str]:
        run = await self.get_run(session_id=session_id, run_id=run_id, tenant_id=tenant_id)
        async with self._lock:
            # Return a copy so stream consumers can iterate without lock contention.
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

        run = await self.get_run(session_id=session_id, run_id=run_id, tenant_id=tenant_id)
        async with self._lock:
            for idx, event in enumerate(run.events):
                if event["event_id"] == last_event_id:
                    return idx + 1
        return 0

    async def _run_worker(self) -> None:
        """Process queued runs in order."""
        while not self._stop_requested:
            session_id, run_id = await self._run_queue.get()
            if session_id is None or run_id is None:
                self._run_queue.task_done()
                break
            await self._execute_stub_run(session_id=session_id, run_id=run_id)
            self._run_queue.task_done()

    async def _execute_stub_run(self, session_id: str, run_id: str) -> None:
        """Emit deterministic events with approval/interrupt semantics."""
        try:
            await self._set_run_status(session_id, run_id, "running")
            await self._append_event(session_id, run_id, "run_started", {"status": "running"})
            if await self._finalize_interrupt_if_requested(session_id, run_id):
                return

            await self._append_event(
                session_id,
                run_id,
                "assistant_delta",
                {"text": "Stub executor: request accepted and being processed."},
            )

            message = await self._get_run_message(session_id, run_id)
            normalized_message = message.lower()
            if "long" in message.lower():
                if not await self._sleep_with_interrupt(session_id, run_id, 1.0):
                    return
            else:
                if not await self._sleep_with_interrupt(session_id, run_id, 0.05):
                    return

            if "gap" in normalized_message or "analy" in normalized_message:
                await self._promote_workflow(session_id, "gap_analyzed")

            if self._message_requires_write(message):
                target_path = self._extract_target_path(message)
                auto_approve = await self._get_session_auto_approve(session_id)
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
                session_id,
                run_id,
                "run_completed",
                {"status": "completed", "final_text": "Stub run completed."},
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
                session_id,
                run_id,
                "failed",
                error={"code": "INTERNAL_ERROR", "message": str(exc)},
            )

    async def _get_run_message(self, session_id: str, run_id: str) -> str:
        run = await self.get_run(session_id=session_id, run_id=run_id)
        return run.message

    async def _get_session_auto_approve(self, session_id: str) -> bool:
        session = await self.get_session(session_id)
        return bool(session.settings.get("auto_approve", False))

    async def _create_approval(self, session_id: str, run_id: str, target_path: str) -> ApprovalRecord:
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise APIError(404, "SESSION_NOT_FOUND", f"Session '{session_id}' not found")
            run = session.runs.get(run_id)
            if not run:
                raise APIError(404, "RUN_NOT_FOUND", f"Run '{run_id}' not found")

            approval_id = make_id("appr")
            approval = ApprovalRecord(
                approval_id=approval_id,
                session_id=session_id,
                run_id=run_id,
                tool_name="file_write",
                args={"path": target_path},
                created_at=utc_now_iso(),
            )
            session.approvals[approval_id] = approval
            session.pending_approvals_count += 1
            run.pending_approval_id = approval_id
            run.wait_event.clear()
        await self._persist_state()
        return approval

    async def _get_approval_status(self, session_id: str, approval_id: str) -> str:
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise APIError(404, "SESSION_NOT_FOUND", f"Session '{session_id}' not found")
            approval = session.approvals.get(approval_id)
            if not approval:
                raise APIError(404, "APPROVAL_NOT_FOUND", f"Approval '{approval_id}' not found")
            return approval.status

    async def _wait_until_approval_or_interrupt(self, session_id: str, run_id: str) -> None:
        while True:
            run = await self.get_run(session_id=session_id, run_id=run_id)
            if run.interrupt_requested or run.pending_approval_id is None:
                return
            await run.wait_event.wait()
            run.wait_event.clear()

    async def _finalize_interrupt_if_requested(self, session_id: str, run_id: str) -> bool:
        run = await self.get_run(session_id=session_id, run_id=run_id)
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

    async def _set_run_status(
        self,
        session_id: str,
        run_id: str,
        status: str,
        error: Optional[Dict[str, Any]] = None,
    ) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return
            run = session.runs.get(run_id)
            if not run:
                return

            run.status = status
            if status == "running" and not run.started_at:
                run.started_at = utc_now_iso()
            if status in TERMINAL_RUN_STATES:
                if run.pending_approval_id:
                    approval = session.approvals.get(run.pending_approval_id)
                    if approval and approval.status == "pending":
                        approval.status = "rejected"
                        approval.decided_at = utc_now_iso()
                        session.pending_approvals_count = max(0, session.pending_approvals_count - 1)
                run.ended_at = utc_now_iso()
                run.error = error
                if not run.usage_finalized:
                    self._finalize_run_usage_locked(run)
                run.pending_approval_id = None
                if session.active_run_id == run_id:
                    session.active_run_id = None
        await self._persist_state()

    async def _append_event(
        self,
        session_id: str,
        run_id: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return
            run = session.runs.get(run_id)
            if not run:
                return

            run.event_seq += 1
            event_id = f"evt_{run_id}_{run.event_seq:04d}"
            run.events.append(
                {
                    "event_id": event_id,
                    "session_id": session_id,
                    "run_id": run_id,
                    "type": event_type,
                    "ts": utc_now_iso(),
                    "payload": payload,
                }
            )
        await self._persist_state()

    def _finalize_run_usage_locked(self, run: RunRecord) -> None:
        text_size = len(run.message or "")
        for event in run.events:
            text_size += len(event.get("type", ""))
            text_size += len(str(event.get("payload", {})))
        estimated_tokens = max(text_size // 4, 1)
        estimated_cost = (estimated_tokens / 1_000_000) * self.cost_per_million_tokens
        run.usage_tokens = estimated_tokens
        run.estimated_cost_usd = round(estimated_cost, 8)
        run.usage_finalized = True

    def _session_for_tenant_locked(self, session_id: str, tenant_id: Optional[str]) -> SessionRecord:
        session = self._sessions.get(session_id)
        if not session:
            raise APIError(404, "SESSION_NOT_FOUND", f"Session '{session_id}' not found")
        if tenant_id and session.tenant_id != tenant_id:
            # Hide cross-tenant existence.
            raise APIError(404, "SESSION_NOT_FOUND", f"Session '{session_id}' not found")
        return session

    def _validate_upload(self, content: bytes, mime_type: Optional[str]) -> None:
        if len(content) > self.max_upload_bytes:
            raise APIError(
                422,
                "UPLOAD_TOO_LARGE",
                "Uploaded file exceeds size limit",
                {"max_upload_bytes": self.max_upload_bytes},
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
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return
            self._promote_workflow_locked(session, state)

    def _promote_workflow_locked(self, session: SessionRecord, state: str) -> None:
        current = WORKFLOW_ORDER.get(session.workflow_state, -1)
        target = WORKFLOW_ORDER.get(state)
        if target is None:
            return
        if target >= current:
            session.workflow_state = state

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

        async with self._lock:
            session = self._sessions.get(session_id)
            if session and (session.resume_path is None or session.resume_path == normalized_path):
                session.resume_path = normalized_path
        await self._persist_state()
        await self._audit(
            action="file_written",
            session_id=session_id,
            run_id=run_id,
            details={
                "path": normalized_path,
                "bytes": written.size,
                "message_preview": message,
            },
        )
        return written

    async def _persist_state(self) -> None:
        if not self.state_file:
            return
        try:
            async with self._persist_lock:
                async with self._lock:
                    payload = self._serialize_state_locked()
                await asyncio.to_thread(self._write_state_file, payload)
        except Exception as exc:
            logger.warning("state_persist_failed path=%s error=%s", self.state_file, exc)

    def _serialize_state_locked(self) -> Dict[str, Any]:
        sessions_payload = [self._serialize_session_locked(session) for session in self._sessions.values()]
        sessions_payload.sort(key=lambda item: item["session_id"])
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "saved_at": utc_now_iso(),
            "sessions": sessions_payload,
        }

    def _serialize_session_locked(self, session: SessionRecord) -> Dict[str, Any]:
        runs = [self._serialize_run_locked(run) for run in session.runs.values()]
        runs.sort(key=lambda item: item["created_at"])
        approvals = [self._serialize_approval_locked(approval) for approval in session.approvals.values()]
        approvals.sort(key=lambda item: item["created_at"])
        return {
            "session_id": session.session_id,
            "tenant_id": session.tenant_id,
            "workspace_name": session.workspace_name,
            "created_at": session.created_at,
            "workflow_state": session.workflow_state,
            "settings": dict(session.settings),
            "active_run_id": session.active_run_id,
            "pending_approvals_count": session.pending_approvals_count,
            "resume_path": session.resume_path,
            "jd_text": session.jd_text,
            "jd_url": session.jd_url,
            "latest_export_path": session.latest_export_path,
            "runs": runs,
            "approvals": approvals,
            "idempotency_keys": dict(session.idempotency_keys),
        }

    def _serialize_run_locked(self, run: RunRecord) -> Dict[str, Any]:
        return {
            "run_id": run.run_id,
            "session_id": run.session_id,
            "message": run.message,
            "status": run.status,
            "created_at": run.created_at,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "error": run.error,
            "events": list(run.events),
            "event_seq": run.event_seq,
            "interrupt_requested": run.interrupt_requested,
            "pending_approval_id": run.pending_approval_id,
            "usage_tokens": run.usage_tokens,
            "estimated_cost_usd": run.estimated_cost_usd,
            "usage_finalized": run.usage_finalized,
        }

    def _serialize_approval_locked(self, approval: ApprovalRecord) -> Dict[str, Any]:
        return {
            "approval_id": approval.approval_id,
            "session_id": approval.session_id,
            "run_id": approval.run_id,
            "tool_name": approval.tool_name,
            "args": dict(approval.args),
            "created_at": approval.created_at,
            "status": approval.status,
            "decided_at": approval.decided_at,
        }

    def _write_state_file(self, payload: Dict[str, Any]) -> None:
        if not self.state_file:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_file.with_suffix(self.state_file.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.state_file)

    async def _load_state(self) -> None:
        if not self.state_file or not self.state_file.exists():
            return
        try:
            raw = await asyncio.to_thread(self.state_file.read_text, "utf-8")
            payload = json.loads(raw)
        except Exception as exc:
            logger.warning("state_load_failed path=%s error=%s", self.state_file, exc)
            return

        sessions = self._deserialize_sessions(payload)
        async with self._lock:
            self._sessions = sessions

        # Persist any startup normalization so subsequent restarts are deterministic.
        await self._persist_state()

    def _deserialize_sessions(self, payload: Dict[str, Any]) -> Dict[str, SessionRecord]:
        schema_version = int(payload.get("schema_version", 1))
        if schema_version > STATE_SCHEMA_VERSION:
            logger.warning(
                "state_schema_unsupported file_schema=%s current_schema=%s",
                schema_version,
                STATE_SCHEMA_VERSION,
            )
            return {}

        raw_sessions = payload.get("sessions", [])
        if isinstance(raw_sessions, dict):
            raw_sessions = list(raw_sessions.values())
        if not isinstance(raw_sessions, list):
            return {}

        loaded: Dict[str, SessionRecord] = {}
        for raw_session in raw_sessions:
            if not isinstance(raw_session, dict):
                continue
            session = self._deserialize_session(raw_session)
            if session:
                loaded[session.session_id] = session
        return loaded

    def _deserialize_session(self, data: Dict[str, Any]) -> Optional[SessionRecord]:
        session_id = str(data.get("session_id", "")).strip()
        tenant_id = str(data.get("tenant_id", "")).strip() or "local-dev"
        if not session_id:
            return None

        raw_settings = data.get("settings", {})
        settings = dict(raw_settings) if isinstance(raw_settings, dict) else {}

        raw_idempotency = data.get("idempotency_keys", {})
        idempotency_keys: Dict[str, Tuple[str, str]] = {}
        if isinstance(raw_idempotency, dict):
            for key, value in raw_idempotency.items():
                if (
                    isinstance(key, str)
                    and isinstance(value, (list, tuple))
                    and len(value) == 2
                    and isinstance(value[0], str)
                    and isinstance(value[1], str)
                ):
                    idempotency_keys[key] = (value[0], value[1])

        session = SessionRecord(
            session_id=session_id,
            tenant_id=tenant_id,
            workspace_name=str(data.get("workspace_name", "default-workspace")),
            created_at=str(data.get("created_at", utc_now_iso())),
            workflow_state=str(data.get("workflow_state", "draft")),
            settings=settings,
            active_run_id=data.get("active_run_id"),
            pending_approvals_count=int(data.get("pending_approvals_count", 0) or 0),
            resume_path=data.get("resume_path"),
            jd_text=data.get("jd_text"),
            jd_url=data.get("jd_url"),
            latest_export_path=data.get("latest_export_path"),
            idempotency_keys=idempotency_keys,
        )

        for run_data in data.get("runs", []):
            run = self._deserialize_run(run_data, session_id=session_id)
            if run:
                session.runs[run.run_id] = run

        for approval_data in data.get("approvals", []):
            approval = self._deserialize_approval(approval_data, session_id=session_id)
            if approval:
                session.approvals[approval.approval_id] = approval

        self._normalize_loaded_session(session)
        return session

    def _deserialize_run(self, data: Any, session_id: str) -> Optional[RunRecord]:
        if not isinstance(data, dict):
            return None
        run_id = str(data.get("run_id", "")).strip()
        if not run_id:
            return None
        raw_events = data.get("events", [])
        events = [event for event in raw_events if isinstance(event, dict)] if isinstance(raw_events, list) else []
        return RunRecord(
            run_id=run_id,
            session_id=session_id,
            message=str(data.get("message", "")),
            status=str(data.get("status", "completed")),
            created_at=str(data.get("created_at", utc_now_iso())),
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
            error=data.get("error"),
            events=events,
            event_seq=int(data.get("event_seq", len(events)) or 0),
            interrupt_requested=bool(data.get("interrupt_requested", False)),
            pending_approval_id=data.get("pending_approval_id"),
            usage_tokens=int(data.get("usage_tokens", 0) or 0),
            estimated_cost_usd=float(data.get("estimated_cost_usd", 0.0) or 0.0),
            usage_finalized=bool(data.get("usage_finalized", False)),
        )

    def _deserialize_approval(self, data: Any, session_id: str) -> Optional[ApprovalRecord]:
        if not isinstance(data, dict):
            return None
        approval_id = str(data.get("approval_id", "")).strip()
        if not approval_id:
            return None
        return ApprovalRecord(
            approval_id=approval_id,
            session_id=session_id,
            run_id=str(data.get("run_id", "")),
            tool_name=str(data.get("tool_name", "file_write")),
            args=dict(data.get("args", {})),
            created_at=str(data.get("created_at", utc_now_iso())),
            status=str(data.get("status", "pending")),
            decided_at=data.get("decided_at"),
        )

    def _normalize_loaded_session(self, session: SessionRecord) -> None:
        now = utc_now_iso()

        for run in session.runs.values():
            # We cannot resume in-flight jobs across process restarts in the in-memory worker,
            # so active runs are deterministically marked interrupted.
            if run.status in ACTIVE_RUN_STATES:
                run.status = "interrupted"
                run.interrupt_requested = True
                run.pending_approval_id = None
                if not run.started_at:
                    run.started_at = run.created_at
                if not run.ended_at:
                    run.ended_at = now
                if not any(event.get("type") == "run_interrupted" for event in run.events):
                    run.event_seq = max(run.event_seq, len(run.events))
                    run.event_seq += 1
                    run.events.append(
                        {
                            "event_id": f"evt_{run.run_id}_{run.event_seq:04d}",
                            "session_id": session.session_id,
                            "run_id": run.run_id,
                            "type": "run_interrupted",
                            "ts": now,
                            "payload": {"status": "interrupted", "reason": "process_restarted"},
                        }
                    )
            if run.event_seq < len(run.events):
                run.event_seq = len(run.events)
            if run.status in TERMINAL_RUN_STATES and not run.usage_finalized:
                self._finalize_run_usage_locked(run)

        for approval in session.approvals.values():
            run = session.runs.get(approval.run_id)
            is_orphaned = run is None
            is_inactive = run and run.status in TERMINAL_RUN_STATES
            no_longer_pending = run and run.pending_approval_id != approval.approval_id
            if approval.status == "pending" and (is_orphaned or is_inactive or no_longer_pending):
                approval.status = "rejected"
                approval.decided_at = now

        session.pending_approvals_count = sum(1 for item in session.approvals.values() if item.status == "pending")
        if session.active_run_id:
            active = session.runs.get(session.active_run_id)
            if not active or active.status in TERMINAL_RUN_STATES:
                session.active_run_id = None

    async def cleanup_expired_resources(self) -> Dict[str, int]:
        """Cleanup expired session/workspace/artifact resources."""
        removed_sessions: List[str] = []

        if self.session_ttl_seconds > 0:
            now = datetime.now(timezone.utc).timestamp()
            async with self._lock:
                for session_id, session in list(self._sessions.items()):
                    if session.active_run_id:
                        active = session.runs.get(session.active_run_id)
                        if active and active.status in ACTIVE_RUN_STATES:
                            continue
                    try:
                        created_epoch = datetime.fromisoformat(session.created_at.replace("Z", "+00:00")).timestamp()
                    except ValueError:
                        # If parsing fails, keep the session to avoid accidental data loss.
                        logger.warning("skip_cleanup_invalid_timestamp session_id=%s", session_id)
                        continue
                    if now - created_epoch >= self.session_ttl_seconds:
                        removed_sessions.append(session_id)
                        del self._sessions[session_id]

        removed_workspace_files = 0
        removed_artifact_files = 0
        for session_id in removed_sessions:
            removed_workspace_files += await self._workspace_provider.delete_workspace(session_id=session_id)
            if self._artifact_storage_provider:
                removed_artifact_files += await self._artifact_storage_provider.delete_artifacts_for_session(
                    session_id=session_id
                )

        if self.artifact_ttl_seconds > 0 and self._artifact_storage_provider:
            removed_artifact_files += await self._artifact_storage_provider.cleanup_expired(
                ttl_seconds=self.artifact_ttl_seconds
            )

        if removed_sessions or removed_artifact_files:
            await self._persist_state()

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
