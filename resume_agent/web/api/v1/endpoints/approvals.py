"""Approval endpoints for tool-call gate."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..deps import get_store
from ....store import ApprovalRecord, InMemoryRuntimeStore

router = APIRouter(prefix="/sessions/{session_id}", tags=["approvals"])


class ApprovalItem(BaseModel):
    approval_id: str
    run_id: str
    tool_name: str
    args: dict
    created_at: str
    status: str


class ListApprovalsResponse(BaseModel):
    items: list[ApprovalItem]


class ApproveRequest(BaseModel):
    apply_to_future: bool = Field(default=False)


class ApprovalActionResponse(BaseModel):
    approval_id: str
    run_id: str
    status: str


@router.get("/approvals", response_model=ListApprovalsResponse)
async def list_approvals(
    session_id: str,
    store: InMemoryRuntimeStore = Depends(get_store),
) -> ListApprovalsResponse:
    approvals = await store.list_pending_approvals(session_id=session_id)
    return ListApprovalsResponse(items=[_to_item(record) for record in approvals])


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalActionResponse)
async def approve(
    session_id: str,
    approval_id: str,
    request: ApproveRequest,
    store: InMemoryRuntimeStore = Depends(get_store),
) -> ApprovalActionResponse:
    approval = await store.approve_approval(
        session_id=session_id,
        approval_id=approval_id,
        apply_to_future=request.apply_to_future,
    )
    return ApprovalActionResponse(
        approval_id=approval.approval_id,
        run_id=approval.run_id,
        status=approval.status,
    )


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalActionResponse)
async def reject(
    session_id: str,
    approval_id: str,
    store: InMemoryRuntimeStore = Depends(get_store),
) -> ApprovalActionResponse:
    approval = await store.reject_approval(session_id=session_id, approval_id=approval_id)
    return ApprovalActionResponse(
        approval_id=approval.approval_id,
        run_id=approval.run_id,
        status=approval.status,
    )


def _to_item(record: ApprovalRecord) -> ApprovalItem:
    return ApprovalItem(
        approval_id=record.approval_id,
        run_id=record.run_id,
        tool_name=record.tool_name,
        args=record.args,
        created_at=record.created_at,
        status=record.status,
    )
