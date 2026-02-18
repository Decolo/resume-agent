"""RuntimeStore protocol — the contract both InMemory and SQLite stores implement."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple, runtime_checkable

from typing_extensions import Protocol

# ---------------------------------------------------------------------------
# Re-export record types so endpoint code can import from one place.
# ---------------------------------------------------------------------------
from .store import ApprovalRecord, RunRecord, SessionRecord  # noqa: F401
from .workspace import WorkspaceFile, WorkspaceFileContent


@runtime_checkable
class RuntimeStore(Protocol):
    """Public surface consumed by API endpoints and middleware."""

    # -- config attributes accessed directly by endpoints --------------------
    provider_name: str
    model_name: str
    max_upload_bytes: int
    allowed_upload_mime_types: Set[str]

    # -- lifecycle -----------------------------------------------------------
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    # -- sessions ------------------------------------------------------------
    async def create_session(self, workspace_name: str, auto_approve: bool, tenant_id: str) -> SessionRecord: ...

    async def get_session(self, session_id: str, tenant_id: Optional[str] = None) -> SessionRecord: ...

    async def set_auto_approve(
        self, session_id: str, enabled: bool, tenant_id: Optional[str] = None
    ) -> Dict[str, bool]: ...

    async def upload_resume(
        self,
        session_id: str,
        filename: str,
        content: bytes,
        mime_type: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> WorkspaceFile: ...

    async def submit_jd(
        self,
        session_id: str,
        text: Optional[str],
        url: Optional[str],
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Optional[str]]: ...

    async def export_session(self, session_id: str, tenant_id: Optional[str] = None) -> WorkspaceFile: ...

    # -- runs ----------------------------------------------------------------
    async def create_run(
        self,
        session_id: str,
        message: str,
        idempotency_key: Optional[str],
        tenant_id: Optional[str] = None,
    ) -> Tuple[RunRecord, bool]: ...

    async def get_run(self, session_id: str, run_id: str, tenant_id: Optional[str] = None) -> RunRecord: ...

    async def interrupt_run(self, session_id: str, run_id: str, tenant_id: Optional[str] = None) -> RunRecord: ...

    async def get_session_usage(self, session_id: str, tenant_id: Optional[str] = None) -> Dict[str, Any]: ...

    # -- events / streaming --------------------------------------------------
    async def snapshot_events(
        self, session_id: str, run_id: str, tenant_id: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], str]: ...

    async def event_index_after(
        self,
        session_id: str,
        run_id: str,
        last_event_id: Optional[str],
        tenant_id: Optional[str] = None,
    ) -> int: ...

    # -- approvals -----------------------------------------------------------
    async def list_pending_approvals(
        self, session_id: str, tenant_id: Optional[str] = None
    ) -> List[ApprovalRecord]: ...

    async def approve_approval(
        self,
        session_id: str,
        approval_id: str,
        apply_to_future: bool,
        tenant_id: Optional[str] = None,
    ) -> ApprovalRecord: ...

    async def reject_approval(
        self, session_id: str, approval_id: str, tenant_id: Optional[str] = None
    ) -> ApprovalRecord: ...

    # -- files ---------------------------------------------------------------
    async def upload_session_file(
        self,
        session_id: str,
        filename: str,
        content: bytes,
        mime_type: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> WorkspaceFile: ...

    async def list_session_files(self, session_id: str, tenant_id: Optional[str] = None) -> List[WorkspaceFile]: ...

    async def read_session_file(
        self, session_id: str, file_path: str, tenant_id: Optional[str] = None
    ) -> WorkspaceFileContent: ...

    # -- settings / metrics --------------------------------------------------
    def runtime_metadata(self) -> Dict[str, Any]: ...

    def get_provider_policy(self) -> Dict[str, Any]: ...

    async def get_runtime_metrics(self) -> Dict[str, Any]: ...

    async def get_alerts(self) -> List[Dict[str, Any]]: ...

    async def cleanup_expired_resources(self) -> Dict[str, int]: ...
