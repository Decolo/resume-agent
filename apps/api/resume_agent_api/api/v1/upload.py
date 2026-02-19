"""Upload helpers for request-size enforcement before full buffering."""

from __future__ import annotations

from fastapi import UploadFile

from ...errors import APIError


async def read_upload_with_limit(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload stream with hard byte limit.

    This prevents loading arbitrarily large payloads into memory before validation.
    """
    chunks: list[bytes] = []
    total = 0
    chunk_size = 64 * 1024

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise APIError(
                422,
                "UPLOAD_TOO_LARGE",
                "Uploaded file exceeds size limit",
                {"max_upload_bytes": max_bytes},
            )
        chunks.append(chunk)

    return b"".join(chunks)
