"""Workspace provider abstraction for web API sessions."""

from __future__ import annotations

import asyncio
import mimetypes
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .errors import APIError


def _utc_iso_from_epoch(epoch_seconds: float) -> str:
    dt = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class WorkspaceFile:
    """File metadata exposed by web API endpoints."""

    path: str
    size: int
    updated_at: str
    mime_type: str


@dataclass
class WorkspaceFileContent:
    """Binary payload + MIME type for file reads."""

    path: str
    content: bytes
    mime_type: str


class WorkspaceProvider(ABC):
    """Storage contract for per-session workspace files."""

    @abstractmethod
    async def create_workspace(self, session_id: str, workspace_name: str) -> None:
        """Initialize storage for a new session."""

    @abstractmethod
    async def save_uploaded_file(self, session_id: str, filename: str, content: bytes) -> WorkspaceFile:
        """Persist one uploaded file into a session workspace."""

    @abstractmethod
    async def list_files(self, session_id: str) -> List[WorkspaceFile]:
        """List files currently stored in a session workspace."""

    @abstractmethod
    async def read_file(self, session_id: str, relative_path: str) -> WorkspaceFileContent:
        """Read a file from a session workspace."""


class RemoteWorkspaceProvider(WorkspaceProvider):
    """Remote-workspace abstraction backed by local disk for Phase 1."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()

    async def create_workspace(self, session_id: str, workspace_name: str) -> None:
        # Keep workspace_name for future metadata use; session_id drives isolation now.
        _ = workspace_name
        await asyncio.to_thread(self._ensure_session_dir, session_id)

    async def save_uploaded_file(self, session_id: str, filename: str, content: bytes) -> WorkspaceFile:
        clean_name = Path(filename).name.strip()
        if not clean_name:
            raise APIError(400, "BAD_REQUEST", "Uploaded file must include a filename")

        target = self._resolve_session_path(session_id, clean_name)

        def _write_file() -> WorkspaceFile:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            stat = target.stat()
            mime_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            return WorkspaceFile(
                path=clean_name,
                size=stat.st_size,
                updated_at=_utc_iso_from_epoch(stat.st_mtime),
                mime_type=mime_type,
            )

        return await asyncio.to_thread(_write_file)

    async def list_files(self, session_id: str) -> List[WorkspaceFile]:
        session_root = await asyncio.to_thread(self._ensure_session_dir, session_id)

        def _collect() -> List[WorkspaceFile]:
            items: List[WorkspaceFile] = []
            for file_path in session_root.rglob("*"):
                if not file_path.is_file():
                    continue
                rel_path = file_path.relative_to(session_root).as_posix()
                stat = file_path.stat()
                mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
                items.append(
                    WorkspaceFile(
                        path=rel_path,
                        size=stat.st_size,
                        updated_at=_utc_iso_from_epoch(stat.st_mtime),
                        mime_type=mime_type,
                    )
                )
            items.sort(key=lambda entry: entry.path)
            return items

        return await asyncio.to_thread(_collect)

    async def read_file(self, session_id: str, relative_path: str) -> WorkspaceFileContent:
        target = self._resolve_session_path(session_id, relative_path)

        def _read() -> WorkspaceFileContent:
            if not target.exists() or not target.is_file():
                raise APIError(404, "FILE_NOT_FOUND", f"File '{relative_path}' not found")
            content = target.read_bytes()
            mime_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            return WorkspaceFileContent(path=relative_path, content=content, mime_type=mime_type)

        return await asyncio.to_thread(_read)

    def _ensure_session_dir(self, session_id: str) -> Path:
        session_root = (self.root_dir / session_id).resolve()
        session_root.mkdir(parents=True, exist_ok=True)
        return session_root

    def _resolve_session_path(self, session_id: str, relative_path: str) -> Path:
        candidate = relative_path.strip()
        if not candidate:
            raise APIError(422, "INVALID_PATH", "File path cannot be empty")

        session_root = self._ensure_session_dir(session_id)
        requested = Path(candidate)
        if requested.is_absolute():
            raise APIError(422, "INVALID_PATH", "Absolute file paths are not allowed")

        resolved = (session_root / requested).resolve()
        try:
            resolved.relative_to(session_root)
        except ValueError as exc:
            raise APIError(422, "INVALID_PATH", "Path escapes session workspace sandbox") from exc
        return resolved


# Backward-compatible name used during early Web API scaffolding.
LocalWorkspaceProvider = RemoteWorkspaceProvider
