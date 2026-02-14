"""File APIs for per-session workspace operations."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from ..deps import get_store
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


@router.post("/files/upload", response_model=UploadFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    session_id: str,
    file: UploadFile = File(...),
    store: InMemoryRuntimeStore = Depends(get_store),
) -> UploadFileResponse:
    content = await file.read()
    metadata = await store.upload_session_file(
        session_id=session_id,
        filename=file.filename or "",
        content=content,
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
) -> ListFilesResponse:
    files = await store.list_session_files(session_id=session_id)
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
) -> Response:
    content = await store.read_session_file(session_id=session_id, file_path=file_path)
    return Response(content=content.content, media_type=content.mime_type)
