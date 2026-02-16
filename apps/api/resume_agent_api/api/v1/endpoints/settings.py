"""Operational settings/introspection endpoints."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from packages.contracts.resume_agent_contracts.web.settings import (
    CleanupResponse,
    FallbackModelResponse,
    ProviderPolicyResponse,
    RetryPolicyResponse,
)

from ....store import InMemoryRuntimeStore
from ..deps import get_store

router = APIRouter(prefix="/settings", tags=["settings"])


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
