"""Wire message types — plain dataclasses for Phase 1."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Union

from resume_agent.providers.types import FunctionCall

# ── Events ──────────────────────────────────────────────────────────


@dataclass
class TurnBegin:
    """Beginning of a new agent turn."""

    user_input: str


@dataclass
class TurnEnd:
    """End of the current agent turn."""

    final_text: str


@dataclass
class StepBegin:
    """Beginning of a new agent step."""

    n: int


@dataclass
class StepInterrupted:
    """Step was interrupted (user cancel or error)."""

    reason: str


@dataclass
class TextDelta:
    """Streaming text chunk from the LLM."""

    text: str


@dataclass
class ToolCallEvent:
    """Tool about to execute."""

    name: str
    arguments: Dict[str, Any]
    call_id: Optional[str] = None


@dataclass
class ToolResultEvent:
    """Tool finished execution."""

    name: str
    result: str
    call_id: Optional[str] = None
    success: bool = True


@dataclass
class StatusUpdate:
    """Status metrics update."""

    step: int = 0
    tokens_used: int = 0


# ── Requests (embed asyncio.Future) ────────────────────────────────


ApprovalResponseKind = Literal["approve", "approve_all", "reject"]


@dataclass
class ApprovalRequest:
    """Request for user approval before executing a gated tool action."""

    id: str
    action: str
    tool_calls: List[FunctionCall]
    description: str
    _future: asyncio.Future = field(default=None, repr=False, compare=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._future is None:
            try:
                loop = asyncio.get_running_loop()
                self._future = loop.create_future()
            except RuntimeError:
                # No running loop — defer future creation to wait()
                pass

    def _get_future(self) -> asyncio.Future[ApprovalResponseKind]:
        if self._future is None:
            self._future = asyncio.get_running_loop().create_future()
        return self._future

    async def wait(self) -> ApprovalResponseKind:
        """Block until the UI resolves this request."""
        return await self._get_future()

    def resolve(self, response: ApprovalResponseKind) -> None:
        """Resolve this request from the UI side."""
        future = self._get_future()
        if not future.done():
            future.set_result(response)


@dataclass
class ApprovalResponse:
    """Acknowledgement that an approval was resolved."""

    request_id: str
    response: ApprovalResponseKind


# ── Union type ──────────────────────────────────────────────────────

WireMessage = Union[
    TurnBegin,
    TurnEnd,
    StepBegin,
    StepInterrupted,
    TextDelta,
    ToolCallEvent,
    ToolResultEvent,
    ApprovalRequest,
    ApprovalResponse,
    StatusUpdate,
]
