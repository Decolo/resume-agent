"""Session endpoints for Web API v1."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from ..deps import get_store
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


class SetAutoApproveRequest(BaseModel):
    enabled: bool = Field(default=False)


class SetAutoApproveResponse(BaseModel):
    enabled: bool


@router.post("", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    store: InMemoryRuntimeStore = Depends(get_store),
) -> CreateSessionResponse:
    session = await store.create_session(
        workspace_name=request.workspace_name,
        auto_approve=request.auto_approve,
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
) -> GetSessionResponse:
    session = await store.get_session(session_id)
    return GetSessionResponse(
        session_id=session.session_id,
        workflow_state=session.workflow_state,
        active_run_id=session.active_run_id,
        pending_approvals_count=session.pending_approvals_count,
        settings=session.settings,
    )


@router.post("/{session_id}/settings/auto-approve", response_model=SetAutoApproveResponse)
async def set_auto_approve(
    session_id: str,
    request: SetAutoApproveRequest,
    store: InMemoryRuntimeStore = Depends(get_store),
) -> SetAutoApproveResponse:
    updated = await store.set_auto_approve(session_id=session_id, enabled=request.enabled)
    return SetAutoApproveResponse(enabled=updated["enabled"])
