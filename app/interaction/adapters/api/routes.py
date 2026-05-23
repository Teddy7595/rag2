from fastapi import APIRouter, Request
from pydantic import BaseModel
from starlette.responses import StreamingResponse
from uuid import uuid4

from app.core.app_context import get_app_context_from_request
from app.interaction.adapters.realtime import build_realtime_stream
from app.interaction.application.realtime import RealtimeChatService
from app.interaction.events import (
    InteractionHistoryRequest,
    InteractionMessageRecordRequest,
    InteractionRealtimeInput,
    InteractionSummaryRequest,
    InteractionSessionRequest,
    REQUEST_INTERACTION_MESSAGE_RECORD,
    REQUEST_INTERACTION_MESSAGES,
    REQUEST_INTERACTION_SESSION_MEMORY,
    REQUEST_INTERACTION_SESSION_TOPIC_GRAPH,
    REQUEST_INTERACTION_TURN_METRICS,
    REQUEST_INTERACTION_SUMMARY,
)


class InteractionMessageInput(BaseModel):
    author: str
    content: str
    channel: str = "chat"
    session_id: str | None = None


class InteractionRealtimeInputModel(BaseModel):
    content: str
    author: str = "user"
    channel: str = "chat"
    identity_id: str | None = None
    context_limit: int = 5
    history_limit: int = 20


router = APIRouter(prefix="/api/interaction", tags=["interaction"])


@router.get("/summary")
async def get_summary(request: Request, limit: int = 5) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_SUMMARY,
        InteractionSummaryRequest(limit=limit),
        source_module="interaction.adapters.api.routes",
    )


@router.get("/messages")
async def list_messages(request: Request, limit: int = 20) -> list[dict[str, object]]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_MESSAGES,
        InteractionHistoryRequest(limit=limit),
        source_module="interaction.adapters.api.routes",
    )


@router.post("/messages")
async def record_message(request: Request, payload: InteractionMessageInput) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_MESSAGE_RECORD,
        InteractionMessageRecordRequest(**payload.model_dump()),
        source_module="interaction.adapters.api.routes",
    )


@router.post("/stream")
async def stream_chat(request: Request, payload: InteractionRealtimeInputModel) -> StreamingResponse:
    context = get_app_context_from_request(request)
    service = context.services.get("interaction_realtime")
    if not isinstance(service, RealtimeChatService):
        raise RuntimeError("Interaction realtime service not registered")

    session_id = request.headers.get("x-session-id") or str(uuid4())
    input_data = InteractionRealtimeInput(**payload.model_dump())
    stream = build_realtime_stream(service, input_data, session_id=session_id)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/sessions/{session_id}/memory")
async def session_memory(request: Request, session_id: str, limit: int = 20) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_SESSION_MEMORY,
        InteractionSessionRequest(session_id=session_id, limit=limit),
        source_module="interaction.adapters.api.routes",
    )


@router.get("/sessions/{session_id}/topics")
async def session_topic_graph(request: Request, session_id: str, limit: int = 20) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_SESSION_TOPIC_GRAPH,
        InteractionSessionRequest(session_id=session_id, limit=limit),
        source_module="interaction.adapters.api.routes",
    )


@router.get("/sessions/{session_id}/metrics")
async def session_turn_metrics(request: Request, session_id: str, limit: int = 20) -> list[dict[str, object]]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_TURN_METRICS,
        InteractionSessionRequest(session_id=session_id, limit=limit),
        source_module="interaction.adapters.api.routes",
    )