"""Session endpoints for Web API v1."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile, status
from pydantic import BaseModel, Field

from ..deps import get_store, get_tenant_id
from ..upload import read_upload_with_limit
from ....store import InMemoryRuntimeStore

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    workspace_name: str = Field(default="default-workspace")
    auto_approve: bool = Field(default=False)


class CreateSessionResponse(BaseModel):
    session_id: str
    created_at: str
    workflow_state: str
    settings: dict


class GetSessionResponse(BaseModel):
    session_id: str
    workflow_state: str
    active_run_id: Optional[str]
    pending_approvals_count: int
    settings: dict
    resume_path: Optional[str] = None
    jd_text: Optional[str] = None
    jd_url: Optional[str] = None
    latest_export_path: Optional[str] = None


class SetAutoApproveRequest(BaseModel):
    enabled: bool = Field(default=False)


class SetAutoApproveResponse(BaseModel):
    enabled: bool


class UploadResumeResponse(BaseModel):
    path: str
    size: int
    mime_type: str
    workflow_state: str


class SubmitJDRequest(BaseModel):
    text: Optional[str] = None
    url: Optional[str] = None


class SubmitJDResponse(BaseModel):
    workflow_state: str
    jd_text: Optional[str] = None
    jd_url: Optional[str] = None


@router.post("", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    store: InMemoryRuntimeStore = Depends(get_store),
    tenant_id: str = Depends(get_tenant_id),
) -> CreateSessionResponse:
    session = await store.create_session(
        workspace_name=request.workspace_name,
        auto_approve=request.auto_approve,
        tenant_id=tenant_id,
    )
    return CreateSessionResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        workflow_state=session.workflow_state,
        settings=session.settings,
    )


@router.get("/{session_id}", response_model=GetSessionResponse)
async def get_session(
    session_id: str,
    store: InMemoryRuntimeStore = Depends(get_store),
    tenant_id: str = Depends(get_tenant_id),
) -> GetSessionResponse:
    session = await store.get_session(session_id, tenant_id=tenant_id)
    return GetSessionResponse(
        session_id=session.session_id,
        workflow_state=session.workflow_state,
        active_run_id=session.active_run_id,
        pending_approvals_count=session.pending_approvals_count,
        settings=session.settings,
        resume_path=session.resume_path,
        jd_text=session.jd_text,
        jd_url=session.jd_url,
        latest_export_path=session.latest_export_path,
    )


@router.post("/{session_id}/settings/auto-approve", response_model=SetAutoApproveResponse)
async def set_auto_approve(
    session_id: str,
    request: SetAutoApproveRequest,
    store: InMemoryRuntimeStore = Depends(get_store),
    tenant_id: str = Depends(get_tenant_id),
) -> SetAutoApproveResponse:
    updated = await store.set_auto_approve(
        session_id=session_id,
        enabled=request.enabled,
        tenant_id=tenant_id,
    )
    return SetAutoApproveResponse(enabled=updated["enabled"])


@router.post("/{session_id}/resume", response_model=UploadResumeResponse, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    session_id: str,
    file: UploadFile = File(...),
    store: InMemoryRuntimeStore = Depends(get_store),
    tenant_id: str = Depends(get_tenant_id),
) -> UploadResumeResponse:
    content = await read_upload_with_limit(file=file, max_bytes=store.max_upload_bytes)
    metadata = await store.upload_resume(
        session_id=session_id,
        filename=file.filename or "",
        content=content,
        mime_type=file.content_type,
        tenant_id=tenant_id,
    )
    session = await store.get_session(session_id=session_id, tenant_id=tenant_id)
    return UploadResumeResponse(
        path=metadata.path,
        size=metadata.size,
        mime_type=metadata.mime_type,
        workflow_state=session.workflow_state,
    )


@router.post("/{session_id}/jd", response_model=SubmitJDResponse)
async def submit_jd(
    session_id: str,
    request: SubmitJDRequest,
    store: InMemoryRuntimeStore = Depends(get_store),
    tenant_id: str = Depends(get_tenant_id),
) -> SubmitJDResponse:
    result = await store.submit_jd(
        session_id=session_id,
        text=request.text,
        url=request.url,
        tenant_id=tenant_id,
    )
    return SubmitJDResponse(
        workflow_state=result["workflow_state"],
        jd_text=result["jd_text"],
        jd_url=result["jd_url"],
    )
