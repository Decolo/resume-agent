"""Approval subsystem — gates write-tool execution on user consent.

Adapted from kimi-cli's soul/approval.py but operates at the agent-loop level
(batch of FunctionCalls) rather than per-tool-call.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Callable, List, Literal, Optional

from typing_extensions import TypeAlias

from resume_agent.providers.types import FunctionCall

from .queue import Queue

Response: TypeAlias = Literal["approve", "approve_all", "reject"]


@dataclass
class Request:
    """An approval request queued for the UI to resolve."""

    id: str
    action: str
    tool_calls: List[FunctionCall]
    description: str


class ApprovalState:
    """Shared mutable state for yolo mode and per-action auto-approve."""

    def __init__(
        self,
        yolo: bool = False,
        auto_approve_actions: Optional[set[str]] = None,
        on_change: Optional[Callable[[], None]] = None,
    ):
        self.yolo = yolo
        self.auto_approve_actions: set[str] = auto_approve_actions or set()
        self._on_change = on_change

    def notify_change(self) -> None:
        if self._on_change is not None:
            self._on_change()


class Approval:
    """Inline approval gate for the agent loop.

    Tools call ``await approval.request(...)`` which blocks until the UI resolves.
    The soul pipes requests to the Wire via ``fetch_request()`` / ``resolve_request()``.
    """

    def __init__(
        self,
        yolo: bool = False,
        *,
        state: Optional[ApprovalState] = None,
    ):
        self._request_queue: Queue[Request] = Queue()
        self._requests: dict[str, tuple[Request, asyncio.Future[bool]]] = {}
        self._state = state or ApprovalState(yolo=yolo)

    def set_yolo(self, yolo: bool) -> None:
        self._state.yolo = yolo
        self._state.notify_change()

    def is_yolo(self) -> bool:
        return self._state.yolo

    async def request(
        self,
        action: str,
        tool_calls: List[FunctionCall],
        description: str,
    ) -> bool:
        """Request approval. Returns True if approved, False if rejected.

        Blocks until the UI calls resolve_request().
        Returns immediately if yolo or action is auto-approved.
        """
        if self._state.yolo:
            return True

        if action in self._state.auto_approve_actions:
            return True

        req = Request(
            id=str(uuid.uuid4()),
            action=action,
            tool_calls=tool_calls,
            description=description,
        )
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._request_queue.put_nowait(req)
        self._requests[req.id] = (req, future)
        return await future

    async def fetch_request(self) -> Request:
        """Fetch next pending request (called by the soul/wire pipe)."""
        while True:
            request = await self._request_queue.get()
            # Auto-approve if the action was approved_all previously
            if request.action in self._state.auto_approve_actions:
                self.resolve_request(request.id, "approve")
                continue
            return request

    def resolve_request(self, request_id: str, response: Response) -> None:
        """Resolve a pending request by ID."""
        entry = self._requests.pop(request_id, None)
        if entry is None:
            raise KeyError(f"No pending request with ID {request_id}")
        request, future = entry

        match response:
            case "approve":
                future.set_result(True)
            case "approve_all":
                self._state.auto_approve_actions.add(request.action)
                self._state.notify_change()
                future.set_result(True)
            case "reject":
                future.set_result(False)
