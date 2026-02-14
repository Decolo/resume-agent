"""Run/message streaming endpoints for Web API v1."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, Header, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..deps import get_store
from ....store import InMemoryRuntimeStore, TERMINAL_RUN_STATES

router = APIRouter(prefix="/sessions/{session_id}", tags=["runs"])
logger = logging.getLogger("resume_agent.web.api")


class CreateMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    idempotency_key: Optional[str] = None


class CreateMessageResponse(BaseModel):
    run_id: str
    status: str


class GetRunResponse(BaseModel):
    run_id: str
    status: str
    started_at: Optional[str]
    ended_at: Optional[str]
    error: Optional[dict]


class InterruptRunResponse(BaseModel):
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
    meta = store.runtime_metadata()
    logger.info(
        "run_created session_id=%s run_id=%s provider=%s model=%s status=%s reused=%s",
        session_id,
        run.run_id,
        meta["provider"],
        meta["model"],
        run.status,
        _is_reused,
    )
    return CreateMessageResponse(run_id=run.run_id, status=run.status)


@router.get("/runs/{run_id}", response_model=GetRunResponse)
async def get_run(
    session_id: str,
    run_id: str,
    store: InMemoryRuntimeStore = Depends(get_store),
) -> GetRunResponse:
    run = await store.get_run(session_id=session_id, run_id=run_id)
    return GetRunResponse(
        run_id=run.run_id,
        status=run.status,
        started_at=run.started_at,
        ended_at=run.ended_at,
        error=run.error,
    )


@router.post("/runs/{run_id}/interrupt", response_model=InterruptRunResponse)
async def interrupt_run(
    session_id: str,
    run_id: str,
    response: Response,
    store: InMemoryRuntimeStore = Depends(get_store),
) -> InterruptRunResponse:
    run = await store.interrupt_run(session_id=session_id, run_id=run_id)
    response.status_code = (
        status.HTTP_200_OK if run.status in TERMINAL_RUN_STATES else status.HTTP_202_ACCEPTED
    )
    return InterruptRunResponse(run_id=run.run_id, status=run.status)


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
