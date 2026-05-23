from fastapi import APIRouter, Request
from pydantic import BaseModel
from starlette.responses import StreamingResponse
from uuid import uuid4

from app.core.app_context import get_app_context_from_request
from app.interaction.adapters.realtime import build_realtime_stream
from app.interaction.application.realtime import RealtimeChatService
from app.interaction.events import (
    InteractionContextTraceRequest,
    InteractionDeletedSessionsRequest,
    InteractionHistoryRequest,
    InteractionMessageActionRequest,
    InteractionMessageRecordRequest,
    InteractionRealtimeInput,
    InteractionSessionConditionsRequest,
    InteractionSessionDeleteRequest,
    InteractionSessionRewindRequest,
    InteractionSummaryRequest,
    InteractionSessionRequest,
    InteractionSessionsRequest,
    REQUEST_INTERACTION_CONTEXT_TRACES,
    REQUEST_INTERACTION_DELETED_SESSIONS,
    REQUEST_INTERACTION_MESSAGE_HIDE,
    REQUEST_INTERACTION_MESSAGE_MEMORIZE,
    REQUEST_INTERACTION_MESSAGE_RECORD,
    REQUEST_INTERACTION_MESSAGES,
    REQUEST_INTERACTION_SESSIONS,
    REQUEST_INTERACTION_SESSION_DELETE,
    REQUEST_INTERACTION_SESSION_RESTORE,
    REQUEST_INTERACTION_SESSION_CONDITIONS,
    REQUEST_INTERACTION_SESSION_CONDITIONS_SET,
    REQUEST_INTERACTION_SESSION_MESSAGES,
    REQUEST_INTERACTION_SESSION_MEMORY,
    REQUEST_INTERACTION_SESSION_REWIND,
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
    saga_id: str | None = None
    context_limit: int = 5
    history_limit: int = 20
    world_rules: str = ""


class InteractionSessionConditionsInput(BaseModel):
    world_rules: str = ""


interaction_router = APIRouter(prefix="/api/interaction", tags=["interaction"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


@interaction_router.get("/summary")
async def get_summary(request: Request, limit: int = 5) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_SUMMARY,
        InteractionSummaryRequest(limit=limit),
        source_module="interaction.adapters.api.routes",
    )


@interaction_router.get("/messages")
async def list_messages(request: Request, limit: int = 20) -> list[dict[str, object]]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_MESSAGES,
        InteractionHistoryRequest(limit=limit),
        source_module="interaction.adapters.api.routes",
    )


@interaction_router.get("/sessions")
async def list_sessions(request: Request, limit: int = 20) -> list[dict[str, object]]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_SESSIONS,
        InteractionSessionsRequest(limit=limit),
        source_module="interaction.adapters.api.routes",
    )


@interaction_router.get("/sessions/deleted")
async def list_deleted_sessions(request: Request, limit: int = 20) -> list[dict[str, object]]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_DELETED_SESSIONS,
        InteractionDeletedSessionsRequest(limit=limit),
        source_module="interaction.adapters.api.routes",
    )


@interaction_router.post("/messages")
async def record_message(request: Request, payload: InteractionMessageInput) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_MESSAGE_RECORD,
        InteractionMessageRecordRequest(**payload.model_dump()),
        source_module="interaction.adapters.api.routes",
    )


@interaction_router.post("/stream")
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


@interaction_router.get("/sessions/{session_id}/memory")
async def session_memory(request: Request, session_id: str, limit: int = 20) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_SESSION_MEMORY,
        InteractionSessionRequest(session_id=session_id, limit=limit),
        source_module="interaction.adapters.api.routes",
    )


@interaction_router.get("/sessions/{session_id}/messages")
async def session_messages(request: Request, session_id: str, limit: int = 50) -> list[dict[str, object]]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_SESSION_MESSAGES,
        InteractionSessionRequest(session_id=session_id, limit=limit),
        source_module="interaction.adapters.api.routes",
    )


@interaction_router.get("/sessions/{session_id}/topics")
async def session_topic_graph(request: Request, session_id: str, limit: int = 20) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_SESSION_TOPIC_GRAPH,
        InteractionSessionRequest(session_id=session_id, limit=limit),
        source_module="interaction.adapters.api.routes",
    )


@interaction_router.get("/sessions/{session_id}/metrics")
async def session_turn_metrics(request: Request, session_id: str, limit: int = 20) -> list[dict[str, object]]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_TURN_METRICS,
        InteractionSessionRequest(session_id=session_id, limit=limit),
        source_module="interaction.adapters.api.routes",
    )


@interaction_router.get("/sessions/{session_id}/conditions")
async def session_conditions(request: Request, session_id: str) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_SESSION_CONDITIONS,
        InteractionSessionRequest(session_id=session_id, limit=1),
        source_module="interaction.adapters.api.routes",
    )


@interaction_router.put("/sessions/{session_id}/conditions")
async def set_session_conditions(
    request: Request,
    session_id: str,
    payload: InteractionSessionConditionsInput,
) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_SESSION_CONDITIONS_SET,
        InteractionSessionConditionsRequest(session_id=session_id, world_rules=payload.world_rules),
        source_module="interaction.adapters.api.routes",
    )


@interaction_router.delete("/messages/{message_id}")
async def hide_message(request: Request, message_id: str) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_MESSAGE_HIDE,
        InteractionMessageActionRequest(message_id=message_id),
        source_module="interaction.adapters.api.routes",
    )


@interaction_router.post("/messages/{message_id}/memorize")
async def memorize_message(request: Request, message_id: str) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_MESSAGE_MEMORIZE,
        InteractionMessageActionRequest(message_id=message_id),
        source_module="interaction.adapters.api.routes",
    )


@interaction_router.post("/sessions/{session_id}/rewind/{message_id}")
async def rewind_session(request: Request, session_id: str, message_id: str) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_SESSION_REWIND,
        InteractionSessionRewindRequest(session_id=session_id, message_id=message_id),
        source_module="interaction.adapters.api.routes",
    )


@interaction_router.delete("/sessions/{session_id}")
async def delete_session(request: Request, session_id: str, hard: bool = False) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_SESSION_DELETE,
        InteractionSessionDeleteRequest(session_id=session_id, hard_delete=hard),
        source_module="interaction.adapters.api.routes",
    )


@interaction_router.post("/sessions/{session_id}/restore")
async def restore_session(request: Request, session_id: str) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_SESSION_RESTORE,
        InteractionSessionDeleteRequest(session_id=session_id),
        source_module="interaction.adapters.api.routes",
    )


@admin_router.get("/context-traces")
async def list_context_traces(
    request: Request,
    trace_id: str | None = None,
    session_id: str | None = None,
    trigger: str | None = None,
    limit: int = 100,
) -> list[dict[str, object]]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_INTERACTION_CONTEXT_TRACES,
        InteractionContextTraceRequest(
            trace_id=trace_id,
            session_id=session_id,
            trigger=trigger,
            limit=limit,
        ),
        source_module="interaction.adapters.api.routes",
    )


router = APIRouter()
router.include_router(interaction_router)
router.include_router(admin_router)