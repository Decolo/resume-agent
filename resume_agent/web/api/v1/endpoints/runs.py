"""Run/message streaming endpoints for Web API v1."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, Header, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..deps import get_store
from ....store import InMemoryRuntimeStore, TERMINAL_RUN_STATES

router = APIRouter(prefix="/sessions/{session_id}", tags=["runs"])


class CreateMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    idempotency_key: Optional[str] = None


class CreateMessageResponse(BaseModel):
    run_id: str
    status: str


@router.post("/messages", response_model=CreateMessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_message_run(
    session_id: str,
    request: CreateMessageRequest,
    store: InMemoryRuntimeStore = Depends(get_store),
) -> CreateMessageResponse:
    run, _is_reused = await store.create_run(
        session_id=session_id,
        message=request.message,
        idempotency_key=request.idempotency_key,
    )
    return CreateMessageResponse(run_id=run.run_id, status=run.status)


@router.get("/runs/{run_id}/stream")
async def stream_run_events(
    session_id: str,
    run_id: str,
    store: InMemoryRuntimeStore = Depends(get_store),
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    # Validate run existence before opening stream.
    await store.get_run(session_id=session_id, run_id=run_id)
    start_index = await store.event_index_after(
        session_id=session_id,
        run_id=run_id,
        last_event_id=last_event_id,
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        cursor = start_index
        while True:
            events, run_status = await store.snapshot_events(session_id=session_id, run_id=run_id)
            if cursor < len(events):
                for event in events[cursor:]:
                    yield format_sse_event(event)
                    cursor += 1

            if run_status in TERMINAL_RUN_STATES and cursor >= len(events):
                break

            await asyncio.sleep(0.05)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


def format_sse_event(event: dict) -> str:
    """Render one event using SSE framing."""
    payload = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
    return f"id: {event['event_id']}\nevent: {event['type']}\ndata: {payload}\n\n"

