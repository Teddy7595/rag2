from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.app_context import get_app_context_from_request
from app.interaction.events import (
    InteractionHistoryRequest,
    InteractionMessageRecordRequest,
    InteractionSummaryRequest,
    REQUEST_INTERACTION_MESSAGE_RECORD,
    REQUEST_INTERACTION_MESSAGES,
    REQUEST_INTERACTION_SUMMARY,
)


class InteractionMessageInput(BaseModel):
    author: str
    content: str
    channel: str = "chat"


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