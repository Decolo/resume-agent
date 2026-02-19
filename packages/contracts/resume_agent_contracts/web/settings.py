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


class RuntimeMetricsResponse(BaseModel):
    sessions: int
    queue_depth: int
    pending_approvals: int
    runs_total: int
    runs_active: int
    runs_completed: int
    runs_failed: int
    runs_interrupted: int
    error_rate: float
    avg_latency_ms: float
    p95_latency_ms: float
    total_tokens: int
    total_estimated_cost_usd: float


class AlertItemResponse(BaseModel):
    name: str
    status: str
    value: float
    threshold: float
    message: str


class AlertsResponse(BaseModel):
    items: list[AlertItemResponse]
