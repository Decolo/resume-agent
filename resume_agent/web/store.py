"""In-memory runtime store for Web API v1."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .errors import APIError

TERMINAL_RUN_STATES = {"completed", "failed", "interrupted"}


def utc_now_iso() -> str:
    """Return current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_id(prefix: str) -> str:
    """Create opaque id matching the documented prefix style."""
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


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

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_RUN_STATES


@dataclass
class SessionRecord:
    session_id: str
    workspace_name: str
    created_at: str
    workflow_state: str
    settings: Dict[str, Any]
    active_run_id: Optional[str] = None
    pending_approvals_count: int = 0
    runs: Dict[str, RunRecord] = field(default_factory=dict)
    idempotency_keys: Dict[str, Tuple[str, str]] = field(default_factory=dict)


class InMemoryRuntimeStore:
    """Minimal runtime persistence for Week 1 APIs."""

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionRecord] = {}
        self._lock = asyncio.Lock()
        self._run_queue: asyncio.Queue[Tuple[Optional[str], Optional[str]]] = asyncio.Queue()
        self._stop_requested = False
        self._worker_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start background run worker."""
        if self._worker_task is None:
            self._stop_requested = False
            self._worker_task = asyncio.create_task(self._run_worker())

    async def stop(self) -> None:
        """Stop background run worker."""
        self._stop_requested = True
        await self._run_queue.put((None, None))
        if self._worker_task:
            await self._worker_task
            self._worker_task = None

    async def create_session(self, workspace_name: str, auto_approve: bool) -> SessionRecord:
        session_id = make_id("sess")
        session = SessionRecord(
            session_id=session_id,
            workspace_name=workspace_name,
            created_at=utc_now_iso(),
            workflow_state="draft",
            settings={"auto_approve": auto_approve},
        )
        async with self._lock:
            self._sessions[session_id] = session
        return session

    async def get_session(self, session_id: str) -> SessionRecord:
        async with self._lock:
            session = self._sessions.get(session_id)
        if not session:
            raise APIError(404, "SESSION_NOT_FOUND", f"Session '{session_id}' not found")
        return session

    async def create_run(
        self,
        session_id: str,
        message: str,
        idempotency_key: Optional[str],
    ) -> Tuple[RunRecord, bool]:
        message_fingerprint = message.strip()

        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise APIError(404, "SESSION_NOT_FOUND", f"Session '{session_id}' not found")

            if session.active_run_id:
                active_run = session.runs.get(session.active_run_id)
                if active_run and not active_run.is_terminal:
                    raise APIError(
                        409,
                        "ACTIVE_RUN_EXISTS",
                        "Session already has an active run",
                        {"run_id": active_run.run_id, "status": active_run.status},
                    )

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
        return run, False

    async def get_run(self, session_id: str, run_id: str) -> RunRecord:
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise APIError(404, "SESSION_NOT_FOUND", f"Session '{session_id}' not found")
            run = session.runs.get(run_id)
            if not run:
                raise APIError(404, "RUN_NOT_FOUND", f"Run '{run_id}' not found")
            return run

    async def snapshot_events(self, session_id: str, run_id: str) -> Tuple[List[Dict[str, Any]], str]:
        run = await self.get_run(session_id=session_id, run_id=run_id)
        async with self._lock:
            # Return a copy so stream consumers can iterate without lock contention.
            return list(run.events), run.status

    async def event_index_after(
        self,
        session_id: str,
        run_id: str,
        last_event_id: Optional[str],
    ) -> int:
        if not last_event_id:
            return 0

        run = await self.get_run(session_id=session_id, run_id=run_id)
        async with self._lock:
            for idx, event in enumerate(run.events):
                if event["event_id"] == last_event_id:
                    return idx + 1
        return 0

    async def _execute_stub_run(self, session_id: str, run_id: str) -> None:
        """Emit deterministic stub events until real executor wiring is added."""
        try:
            await self._set_run_status(session_id, run_id, "running")
            await self._append_event(session_id, run_id, "run_started", {"status": "running"})
            await asyncio.sleep(0.01)
            await self._append_event(
                session_id,
                run_id,
                "assistant_delta",
                {"text": "Stub executor: run accepted and queued for real runtime integration."},
            )
            await asyncio.sleep(0.01)
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

    async def _run_worker(self) -> None:
        """Process queued runs in order."""
        while not self._stop_requested:
            session_id, run_id = await self._run_queue.get()
            if session_id is None or run_id is None:
                self._run_queue.task_done()
                break
            await self._execute_stub_run(session_id=session_id, run_id=run_id)
            self._run_queue.task_done()

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
                run.ended_at = utc_now_iso()
                run.error = error
                if session.active_run_id == run_id:
                    session.active_run_id = None

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
