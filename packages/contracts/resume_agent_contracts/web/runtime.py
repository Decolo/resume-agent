"""Shared runtime constants/types for web API contracts."""

from __future__ import annotations

from typing import Final, Literal, TypeAlias

RunState: TypeAlias = Literal[
    "queued",
    "running",
    "waiting_approval",
    "interrupting",
    "completed",
    "failed",
    "interrupted",
]
WorkflowState: TypeAlias = Literal[
    "draft",
    "resume_uploaded",
    "jd_provided",
    "gap_analyzed",
    "rewrite_applied",
    "exported",
    "cancelled",
]

TERMINAL_RUN_STATES: Final[set[RunState]] = {"completed", "failed", "interrupted"}
ACTIVE_RUN_STATES: Final[set[RunState]] = {"queued", "running", "waiting_approval", "interrupting"}
WORKFLOW_ORDER: Final[dict[WorkflowState, int]] = {
    "draft": 0,
    "resume_uploaded": 1,
    "jd_provided": 2,
    "gap_analyzed": 3,
    "rewrite_applied": 4,
    "exported": 5,
    "cancelled": 6,
}
DEFAULT_ALLOWED_UPLOAD_MIME_TYPES: Final[tuple[str, ...]] = (
    "text/markdown",
    "text/plain",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)
DEFAULT_COST_PER_MILLION_TOKENS: Final[float] = 0.08
