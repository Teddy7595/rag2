from __future__ import annotations

from fastapi import Request
from fastapi.routing import APIRouter

from app.core.app_context import get_app_context_from_request
from app.workshop.events import (
    WorkshopCloseRequest,
    WorkshopCreateRequest,
    WorkshopDeleteRequest,
    WorkshopGetRequest,
    WorkshopListRequest,
    WorkshopPromoteRequest,
    REQUEST_WORKSHOP_CLOSE,
    REQUEST_WORKSHOP_CREATE,
    REQUEST_WORKSHOP_DELETE,
    REQUEST_WORKSHOP_GET,
    REQUEST_WORKSHOP_LIST,
    REQUEST_WORKSHOP_PROMOTE,
)

router = APIRouter(prefix="/api/workshop")


@router.post("/sessions")
async def create_workshop(request: Request) -> dict:
    body = await request.json()
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_WORKSHOP_CREATE,
        WorkshopCreateRequest(
            title=str(body.get("title") or "Taller sin título"),
            engram_id=str(body.get("engram_id") or ""),
            source_documents=list(body.get("source_documents") or []),
            chat_session_id=str(body["chat_session_id"]) if body.get("chat_session_id") else None,
        ),
        source_module="workshop.adapters.api.routes",
    )


@router.get("/sessions")
async def list_workshops(request: Request) -> list:
    context = get_app_context_from_request(request)
    result = context.event_bus.request(
        REQUEST_WORKSHOP_LIST,
        WorkshopListRequest(limit=50),
        source_module="workshop.adapters.api.routes",
    )
    return result if isinstance(result, list) else []


@router.get("/sessions/{workshop_id}")
async def get_workshop(request: Request, workshop_id: str) -> dict:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_WORKSHOP_GET,
        WorkshopGetRequest(workshop_id=workshop_id),
        source_module="workshop.adapters.api.routes",
    )


@router.post("/sessions/{workshop_id}/close")
async def close_workshop(request: Request, workshop_id: str) -> dict:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_WORKSHOP_CLOSE,
        WorkshopCloseRequest(workshop_id=workshop_id),
        source_module="workshop.adapters.api.routes",
    )


@router.post("/sessions/{workshop_id}/promote")
async def promote_workshop(request: Request, workshop_id: str) -> dict:
    body = await request.json()
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_WORKSHOP_PROMOTE,
        WorkshopPromoteRequest(
            workshop_id=workshop_id,
            summary_title=str(body.get("title") or "Resumen del taller"),
            summary_text=str(body.get("summary") or ""),
        ),
        source_module="workshop.adapters.api.routes",
    )


@router.delete("/sessions/{workshop_id}")
async def delete_workshop(request: Request, workshop_id: str) -> dict:
    context = get_app_context_from_request(request)
    result = context.event_bus.request(
        REQUEST_WORKSHOP_DELETE,
        WorkshopDeleteRequest(workshop_id=workshop_id),
        source_module="workshop.adapters.api.routes",
    )
    return result if isinstance(result, dict) else {"deleted": bool(result)}
