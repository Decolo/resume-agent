"""Operational settings/introspection endpoints."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from packages.contracts.resume_agent_contracts.web.settings import (
    AlertItemResponse,
    AlertsResponse,
    CleanupResponse,
    FallbackModelResponse,
    ProviderPolicyResponse,
    RetryPolicyResponse,
    RuntimeMetricsResponse,
)

from ....store_protocol import RuntimeStore
from ..deps import get_store

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/provider-policy", response_model=ProviderPolicyResponse)
async def get_provider_policy(
    store: RuntimeStore = Depends(get_store),
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
    store: RuntimeStore = Depends(get_store),
) -> CleanupResponse:
    result = await store.cleanup_expired_resources()
    return CleanupResponse(**result)


@router.get("/metrics", response_model=RuntimeMetricsResponse)
async def get_runtime_metrics(
    store: RuntimeStore = Depends(get_store),
) -> RuntimeMetricsResponse:
    metrics = await store.get_runtime_metrics()
    return RuntimeMetricsResponse(**metrics)


@router.get("/alerts", response_model=AlertsResponse)
async def get_alerts(
    store: RuntimeStore = Depends(get_store),
) -> AlertsResponse:
    alerts = await store.get_alerts()
    return AlertsResponse(items=[AlertItemResponse(**item) for item in alerts])
