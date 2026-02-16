"""Settings endpoint response contracts."""

from __future__ import annotations

from pydantic import BaseModel


class RetryPolicyResponse(BaseModel):
    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float


class FallbackModelResponse(BaseModel):
    provider: str
    model: str


class ProviderPolicyResponse(BaseModel):
    retry: RetryPolicyResponse
    fallback_chain: list[FallbackModelResponse]


class CleanupResponse(BaseModel):
    removed_sessions: int
    removed_workspace_files: int
    removed_artifact_files: int
