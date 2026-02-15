"""File APIs for per-session workspace operations."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from ..deps import get_store, get_tenant_id
from ..upload import read_upload_with_limit
from ....store import InMemoryRuntimeStore

router = APIRouter(prefix="/sessions/{session_id}", tags=["files"])


class UploadFileResponse(BaseModel):
    file_id: str
    path: str
    size: int
    mime_type: str


class FileItem(BaseModel):
    path: str
    size: int
    updated_at: str


class ListFilesResponse(BaseModel):
    files: list[FileItem]


class ExportResponse(BaseModel):
    artifact_path: str
    size: int
    mime_type: str
    workflow_state: str


@router.post("/files/upload", response_model=UploadFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    session_id: str,
    file: UploadFile = File(...),
    store: InMemoryRuntimeStore = Depends(get_store),
    tenant_id: str = Depends(get_tenant_id),
) -> UploadFileResponse:
    content = await read_upload_with_limit(file=file, max_bytes=store.max_upload_bytes)
    metadata = await store.upload_session_file(
        session_id=session_id,
        filename=file.filename or "",
        content=content,
        mime_type=file.content_type,
        tenant_id=tenant_id,
    )
    return UploadFileResponse(
        file_id=f"file_{uuid.uuid4().hex[:10]}",
        path=metadata.path,
        size=metadata.size,
        mime_type=metadata.mime_type,
    )


@router.get("/files", response_model=ListFilesResponse)
async def list_files(
    session_id: str,
    store: InMemoryRuntimeStore = Depends(get_store),
    tenant_id: str = Depends(get_tenant_id),
) -> ListFilesResponse:
    files = await store.list_session_files(session_id=session_id, tenant_id=tenant_id)
    return ListFilesResponse(
        files=[
            FileItem(path=item.path, size=item.size, updated_at=item.updated_at)
            for item in files
        ]
    )


@router.get("/files/{file_path:path}")
async def get_file(
    session_id: str,
    file_path: str,
    store: InMemoryRuntimeStore = Depends(get_store),
    tenant_id: str = Depends(get_tenant_id),
) -> Response:
    content = await store.read_session_file(
        session_id=session_id,
        file_path=file_path,
        tenant_id=tenant_id,
    )
    return Response(content=content.content, media_type=content.mime_type)


@router.post("/export", response_model=ExportResponse, status_code=status.HTTP_201_CREATED)
async def export_resume(
    session_id: str,
    store: InMemoryRuntimeStore = Depends(get_store),
    tenant_id: str = Depends(get_tenant_id),
) -> ExportResponse:
    artifact = await store.export_session(session_id=session_id, tenant_id=tenant_id)
    session = await store.get_session(session_id=session_id, tenant_id=tenant_id)
    return ExportResponse(
        artifact_path=artifact.path,
        size=artifact.size,
        mime_type=artifact.mime_type,
        workflow_state=session.workflow_state,
    )
