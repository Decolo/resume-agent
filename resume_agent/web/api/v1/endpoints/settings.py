"""Operational settings/introspection endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ....store import InMemoryRuntimeStore
from ..deps import get_store

router = APIRouter(prefix="/settings", tags=["settings"])


class RetryPolicyResponse(BaseModel):
    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float


class FallbackModelResponse(BaseModel):
    provider: str
    model: str


class ProviderPolicyResponse(BaseModel):
    retry: RetryPolicyResponse
    fallback_chain: List[FallbackModelResponse]


class CleanupResponse(BaseModel):
    removed_sessions: int
    removed_workspace_files: int
    removed_artifact_files: int


@router.get("/provider-policy", response_model=ProviderPolicyResponse)
async def get_provider_policy(
    store: InMemoryRuntimeStore = Depends(get_store),
) -> ProviderPolicyResponse:
    policy: Dict[str, Any] = store.get_provider_policy()
    retry: Dict[str, Any] = policy.get("retry", {})
    fallback = policy.get("fallback_chain", [])
    return ProviderPolicyResponse(
        retry=RetryPolicyResponse(
            max_attempts=int(retry.get("max_attempts", 1)),
            base_delay_seconds=float(retry.get("base_delay_seconds", 0.0)),
            max_delay_seconds=float(retry.get("max_delay_seconds", 0.0)),
        ),
        fallback_chain=[
            FallbackModelResponse(
                provider=str(item.get("provider", "")),
                model=str(item.get("model", "")),
            )
            for item in fallback
            if item.get("provider") and item.get("model")
        ],
    )


@router.post("/cleanup", response_model=CleanupResponse)
async def run_cleanup(
    store: InMemoryRuntimeStore = Depends(get_store),
) -> CleanupResponse:
    result = await store.cleanup_expired_resources()
    return CleanupResponse(**result)
