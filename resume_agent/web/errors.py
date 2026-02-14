"""API error helpers and exception handlers."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class APIError(Exception):
    """Application-level API error with status/code mapping."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


async def api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    """Render contract-compliant error response."""
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Normalize FastAPI validation errors to API contract shape."""
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "BAD_REQUEST",
                "message": "Invalid request payload",
                "details": {"errors": exc.errors()},
            }
        },
    )

