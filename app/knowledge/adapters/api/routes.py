from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.app_context import get_app_context_from_request
from app.knowledge.events import (
    KnowledgeItemCreateRequest,
    KnowledgeItemsRequest,
    KnowledgeOverviewRequest,
    REQUEST_KNOWLEDGE_ITEM_CREATE,
    REQUEST_KNOWLEDGE_ITEMS,
    REQUEST_KNOWLEDGE_OVERVIEW,
)


class KnowledgeItemInput(BaseModel):
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/overview")
async def overview(request: Request, limit: int = 5) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_KNOWLEDGE_OVERVIEW,
        KnowledgeOverviewRequest(limit=limit),
        source_module="knowledge.adapters.api.routes",
    )


@router.get("/items")
async def list_items(request: Request, limit: int = 20) -> list[dict[str, object]]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_KNOWLEDGE_ITEMS,
        KnowledgeItemsRequest(limit=limit),
        source_module="knowledge.adapters.api.routes",
    )


@router.post("/items")
async def create_item(request: Request, payload: KnowledgeItemInput) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_KNOWLEDGE_ITEM_CREATE,
        KnowledgeItemCreateRequest(
            title=payload.title,
            content=payload.content,
            tags=tuple(payload.tags),
        ),
        source_module="knowledge.adapters.api.routes",
    )