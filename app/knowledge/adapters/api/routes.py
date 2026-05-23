from fastapi import APIRouter, Request
from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from app.core.app_context import get_app_context_from_request
from app.knowledge.events import (
    ContextBuildRequest,
    ContextRouteRequest,
    CurrentIdentityRequest,
    EngramCreateRequest,
    EngramDeleteRequest,
    EngramHintsRequest,
    EngramListRequest,
    EngramUpdateRequest,
    IdentityResolveRequest,
    KnowledgeItemCreateRequest,
    KnowledgeItemsRequest,
    KnowledgeOverviewRequest,
    REQUEST_KNOWLEDGE_CURRENT_IDENTITY,
    REQUEST_KNOWLEDGE_CONTEXT_PACK,
    REQUEST_KNOWLEDGE_CONTEXT_PROMPT,
    REQUEST_KNOWLEDGE_CONTEXT_ROUTE,
    REQUEST_KNOWLEDGE_ENGRAM_CREATE,
    REQUEST_KNOWLEDGE_ENGRAM_DELETE,
    REQUEST_KNOWLEDGE_ENGRAM_UPDATE,
    REQUEST_KNOWLEDGE_ENGRAMS,
    REQUEST_KNOWLEDGE_IDENTITY_HINTS,
    REQUEST_KNOWLEDGE_IDENTITY_RESOLVE,
    REQUEST_KNOWLEDGE_ITEM_CREATE,
    REQUEST_KNOWLEDGE_ITEMS,
    REQUEST_KNOWLEDGE_OVERVIEW,
)


class KnowledgeItemInput(BaseModel):
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)


class KnowledgeEngramInput(BaseModel):
    name: str
    avatar: str = ""
    color_hex: str = "#00ff41"
    intellectual_profile: str = "General"
    behavior_prompt: str = ""
    meta_rule: str = "Stay consistent with the selected identity."
    moral_threshold: int = 0
    interaction_mode: str = "Directo"
    dialogue_examples: list[str] = Field(default_factory=list)
    backstory: str = ""
    temperatura_base: float = 0.8
    top_p_base: float = 1.0
    max_tokens_respuesta: int = 2048


class KnowledgeEngramUpdateInput(BaseModel):
    name: str | None = None
    avatar: str | None = None
    color_hex: str | None = None
    intellectual_profile: str | None = None
    behavior_prompt: str | None = None
    meta_rule: str | None = None
    moral_threshold: int | None = None
    interaction_mode: str | None = None
    dialogue_examples: list[str] | None = None
    backstory: str | None = None
    temperatura_base: float | None = None
    top_p_base: float | None = None
    max_tokens_respuesta: int | None = None


class KnowledgeIdentityResolveInput(BaseModel):
    raw_text: str
    identity_id: str | None = None


class KnowledgeContextInput(BaseModel):
    raw_text: str
    limit: int = 5
    identity_id: str | None = None
    history: str = ""


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


@router.get("/engrams")
async def list_engrams(request: Request, limit: int = 20) -> list[dict[str, object]]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_KNOWLEDGE_ENGRAMS,
        EngramListRequest(limit=limit),
        source_module="knowledge.adapters.api.routes",
    )


@router.get("/identity/current")
async def current_identity(request: Request) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_KNOWLEDGE_CURRENT_IDENTITY,
        CurrentIdentityRequest(),
        source_module="knowledge.adapters.api.routes",
    )


@router.get("/identity/hints")
async def list_identity_hints(request: Request) -> list[str]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_KNOWLEDGE_IDENTITY_HINTS,
        EngramHintsRequest(),
        source_module="knowledge.adapters.api.routes",
    )


@router.post("/identity/resolve")
async def resolve_identity(request: Request, payload: KnowledgeIdentityResolveInput) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_KNOWLEDGE_IDENTITY_RESOLVE,
        IdentityResolveRequest(raw_text=payload.raw_text, identity_id=payload.identity_id),
        source_module="knowledge.adapters.api.routes",
    )


@router.get("/context/route")
async def route_context(request: Request, raw_text: str, limit: int = 5) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_KNOWLEDGE_CONTEXT_ROUTE,
        ContextRouteRequest(raw_text=raw_text, limit=limit),
        source_module="knowledge.adapters.api.routes",
    )


@router.post("/context/pack")
async def build_context_pack(request: Request, payload: KnowledgeContextInput) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_KNOWLEDGE_CONTEXT_PACK,
        ContextBuildRequest(
            raw_text=payload.raw_text,
            limit=payload.limit,
            identity_id=payload.identity_id,
            history=payload.history,
        ),
        source_module="knowledge.adapters.api.routes",
    )


@router.post("/context/prompt")
async def build_prompt(request: Request, payload: KnowledgeContextInput) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_KNOWLEDGE_CONTEXT_PROMPT,
        ContextBuildRequest(
            raw_text=payload.raw_text,
            limit=payload.limit,
            identity_id=payload.identity_id,
            history=payload.history,
        ),
        source_module="knowledge.adapters.api.routes",
    )


@router.post("/engrams")
async def create_engram(request: Request, payload: KnowledgeEngramInput) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_KNOWLEDGE_ENGRAM_CREATE,
        EngramCreateRequest(
            name=payload.name,
            avatar=payload.avatar,
            color_hex=payload.color_hex,
            intellectual_profile=payload.intellectual_profile,
            behavior_prompt=payload.behavior_prompt,
            meta_rule=payload.meta_rule,
            moral_threshold=payload.moral_threshold,
            interaction_mode=payload.interaction_mode,
            dialogue_examples=tuple(payload.dialogue_examples),
            backstory=payload.backstory,
            temperatura_base=payload.temperatura_base,
            top_p_base=payload.top_p_base,
            max_tokens_respuesta=payload.max_tokens_respuesta,
        ),
        source_module="knowledge.adapters.api.routes",
    )


@router.patch("/engrams/{engram_id}")
async def update_engram(request: Request, engram_id: str, payload: KnowledgeEngramUpdateInput) -> dict[str, object]:
    context = get_app_context_from_request(request)
    result = context.event_bus.request(
        REQUEST_KNOWLEDGE_ENGRAM_UPDATE,
        EngramUpdateRequest(
            engram_id=engram_id,
            name=payload.name,
            avatar=payload.avatar,
            color_hex=payload.color_hex,
            intellectual_profile=payload.intellectual_profile,
            behavior_prompt=payload.behavior_prompt,
            meta_rule=payload.meta_rule,
            moral_threshold=payload.moral_threshold,
            interaction_mode=payload.interaction_mode,
            dialogue_examples=tuple(payload.dialogue_examples) if payload.dialogue_examples is not None else None,
            backstory=payload.backstory,
            temperatura_base=payload.temperatura_base,
            top_p_base=payload.top_p_base,
            max_tokens_respuesta=payload.max_tokens_respuesta,
        ),
        source_module="knowledge.adapters.api.routes",
    )
    if not result["updated"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engram not found")
    return result["engram"]


@router.delete("/engrams/{engram_id}")
async def delete_engram(request: Request, engram_id: str) -> dict[str, object]:
    context = get_app_context_from_request(request)
    result = context.event_bus.request(
        REQUEST_KNOWLEDGE_ENGRAM_DELETE,
        EngramDeleteRequest(engram_id=engram_id),
        source_module="knowledge.adapters.api.routes",
    )
    if not result["deleted"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engram not found")
    return result