"""Artifact storage abstraction for exported session outputs."""

from __future__ import annotations

import asyncio
import mimetypes
import shutil
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .errors import APIError
from .workspace import WorkspaceFile, WorkspaceFileContent


def _utc_iso_from_epoch(epoch_seconds: float) -> str:
    dt = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ArtifactStorageProvider(ABC):
    """Storage contract for exported artifacts."""

    @abstractmethod
    async def write_artifact(self, session_id: str, artifact_path: str, content: bytes) -> WorkspaceFile:
        """Persist an exported artifact for one session."""

    @abstractmethod
    async def read_artifact(self, session_id: str, artifact_path: str) -> WorkspaceFileContent:
        """Read an exported artifact by path."""

    @abstractmethod
    async def list_artifacts(self, session_id: str) -> List[WorkspaceFile]:
        """List artifacts for one session."""

    @abstractmethod
    async def delete_artifacts_for_session(self, session_id: str) -> int:
        """Delete all artifacts for one session."""

    @abstractmethod
    async def cleanup_expired(self, ttl_seconds: int) -> int:
        """Delete artifacts older than TTL, return removed file count."""


class LocalArtifactStorageProvider(ArtifactStorageProvider):
    """Local-disk artifact backend used for local-first web deployment."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()

    async def write_artifact(self, session_id: str, artifact_path: str, content: bytes) -> WorkspaceFile:
        target = self._resolve_artifact_path(session_id=session_id, artifact_path=artifact_path)

        def _write() -> WorkspaceFile:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            stat = target.stat()
            mime_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            normalized_path = Path(artifact_path).as_posix()
            return WorkspaceFile(
                path=normalized_path,
                size=stat.st_size,
                updated_at=_utc_iso_from_epoch(stat.st_mtime),
                mime_type=mime_type,
            )

        return await asyncio.to_thread(_write)

    async def read_artifact(self, session_id: str, artifact_path: str) -> WorkspaceFileContent:
        target = self._resolve_artifact_path(session_id=session_id, artifact_path=artifact_path)

        def _read() -> WorkspaceFileContent:
            if not target.exists() or not target.is_file():
                raise APIError(404, "FILE_NOT_FOUND", f"File '{artifact_path}' not found")
            content = target.read_bytes()
            mime_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            normalized_path = Path(artifact_path).as_posix()
            return WorkspaceFileContent(path=normalized_path, content=content, mime_type=mime_type)

        return await asyncio.to_thread(_read)

    async def list_artifacts(self, session_id: str) -> List[WorkspaceFile]:
        session_root = self._session_root(session_id)
        if not session_root.exists():
            return []

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
            items.sort(key=lambda item: item.path)
            return items

        return await asyncio.to_thread(_collect)

    async def delete_artifacts_for_session(self, session_id: str) -> int:
        session_root = self._session_root(session_id)
        if not session_root.exists():
            return 0

        def _delete() -> int:
            removed = sum(1 for path in session_root.rglob("*") if path.is_file())
            shutil.rmtree(session_root, ignore_errors=True)
            return removed

        return await asyncio.to_thread(_delete)

    async def cleanup_expired(self, ttl_seconds: int) -> int:
        if ttl_seconds <= 0:
            return 0

        cutoff = datetime.now(timezone.utc).timestamp() - ttl_seconds

        def _cleanup() -> int:
            removed = 0
            if not self.root_dir.exists():
                return 0
            for file_path in self.root_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                if file_path.stat().st_mtime < cutoff:
                    file_path.unlink(missing_ok=True)
                    removed += 1

            for directory in sorted(self.root_dir.rglob("*"), reverse=True):
                if directory.is_dir():
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
            return removed

        return await asyncio.to_thread(_cleanup)

    def _session_root(self, session_id: str) -> Path:
        return (self.root_dir / session_id).resolve()

    def _resolve_artifact_path(self, session_id: str, artifact_path: str) -> Path:
        candidate = artifact_path.strip()
        if not candidate:
            raise APIError(422, "INVALID_PATH", "File path cannot be empty")

        relative = Path(candidate)
        if relative.is_absolute():
            raise APIError(422, "INVALID_PATH", "Absolute file paths are not allowed")

        session_root = self._session_root(session_id)
        resolved = (session_root / relative).resolve()
        try:
            resolved.relative_to(session_root)
        except ValueError as exc:
            raise APIError(422, "INVALID_PATH", "Path escapes session artifact sandbox") from exc
        return resolved
