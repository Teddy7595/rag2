from __future__ import annotations

from fastapi import FastAPI

from app.core.app_context import get_app_context_from_app
from app.core.events import EventEnvelope
from app.workshop.events import (
    REQUEST_WORKSHOP_CLOSE,
    REQUEST_WORKSHOP_CREATE,
    REQUEST_WORKSHOP_DELETE,
    REQUEST_WORKSHOP_GET,
    REQUEST_WORKSHOP_LIST,
    REQUEST_WORKSHOP_PROMOTE,
)


def register_workshop_event_handlers(app: FastAPI) -> None:
    context = get_app_context_from_app(app)
    service = context.services.get("workshop")

    def handle_create(envelope: EventEnvelope[object]) -> dict:
        req = envelope.payload
        ws = service.create_session(
            title=req.title,
            engram_id=req.engram_id,
            source_documents=req.source_documents,
            chat_session_id=req.chat_session_id,
        )
        return ws.as_dict()

    def handle_list(envelope: EventEnvelope[object]) -> list:
        sessions = service.list_sessions(limit=envelope.payload.limit)
        return [ws.as_dict() for ws in sessions]

    def handle_get(envelope: EventEnvelope[object]) -> dict:
        ws = service.get_session(envelope.payload.workshop_id)
        return ws.as_dict() if ws else {}

    def handle_close(envelope: EventEnvelope[object]) -> dict:
        ws = service.close_session(envelope.payload.workshop_id)
        return ws.as_dict() if ws else {"ok": False}

    def handle_promote(envelope: EventEnvelope[object]) -> dict:
        req = envelope.payload
        return service.promote(req.workshop_id, req.summary_title, req.summary_text)

    def handle_delete(envelope: EventEnvelope[object]) -> dict:
        deleted = service.delete_session(envelope.payload.workshop_id)
        return {"deleted": deleted}

    context.event_bus.subscribe_request(REQUEST_WORKSHOP_CREATE, handle_create)
    context.event_bus.subscribe_request(REQUEST_WORKSHOP_LIST, handle_list)
    context.event_bus.subscribe_request(REQUEST_WORKSHOP_GET, handle_get)
    context.event_bus.subscribe_request(REQUEST_WORKSHOP_CLOSE, handle_close)
    context.event_bus.subscribe_request(REQUEST_WORKSHOP_PROMOTE, handle_promote)
    context.event_bus.subscribe_request(REQUEST_WORKSHOP_DELETE, handle_delete)
