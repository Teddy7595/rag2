from fastapi import FastAPI

from app.core.app_context import get_app_context_from_app
from app.core.events import EventEnvelope
from app.knowledge.application import KnowledgeService
from app.knowledge.events import (
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


def register_knowledge_event_handlers(app: FastAPI) -> None:
    context = get_app_context_from_app(app)
    service = context.services.get("knowledge")
    if not isinstance(service, KnowledgeService):
        raise RuntimeError("Knowledge service not registered")

    def handle_overview(envelope: EventEnvelope[KnowledgeOverviewRequest]) -> dict[str, object]:
        return service.overview(envelope.payload)

    def handle_items(envelope: EventEnvelope[KnowledgeItemsRequest]) -> list[dict[str, object]]:
        return service.list_items(envelope.payload)

    def handle_create(envelope: EventEnvelope[KnowledgeItemCreateRequest]) -> dict[str, object]:
        return service.create_item(envelope.payload)

    def handle_engrams(envelope: EventEnvelope[EngramListRequest]) -> list[dict[str, object]]:
        return service.list_engrams(envelope.payload)

    def handle_current_identity(envelope: EventEnvelope[CurrentIdentityRequest]) -> dict[str, object]:
        return service.current_identity(envelope.payload)

    def handle_resolve_identity(envelope: EventEnvelope[IdentityResolveRequest]) -> dict[str, object]:
        return service.resolve_identity(envelope.payload)

    def handle_identity_hints(envelope: EventEnvelope[EngramHintsRequest]) -> list[str]:
        return service.list_hint_handles(envelope.payload)

    def handle_create_engram(envelope: EventEnvelope[EngramCreateRequest]) -> dict[str, object]:
        return service.create_engram(envelope.payload)

    def handle_update_engram(envelope: EventEnvelope[EngramUpdateRequest]) -> dict[str, object]:
        return service.update_engram(envelope.payload)

    def handle_delete_engram(envelope: EventEnvelope[EngramDeleteRequest]) -> dict[str, object]:
        return service.delete_engram(envelope.payload)

    context.event_bus.subscribe_request(REQUEST_KNOWLEDGE_OVERVIEW, handle_overview)
    context.event_bus.subscribe_request(REQUEST_KNOWLEDGE_ITEMS, handle_items)
    context.event_bus.subscribe_request(REQUEST_KNOWLEDGE_ITEM_CREATE, handle_create)
    context.event_bus.subscribe_request(REQUEST_KNOWLEDGE_ENGRAMS, handle_engrams)
    context.event_bus.subscribe_request(REQUEST_KNOWLEDGE_CURRENT_IDENTITY, handle_current_identity)
    context.event_bus.subscribe_request(REQUEST_KNOWLEDGE_IDENTITY_RESOLVE, handle_resolve_identity)
    context.event_bus.subscribe_request(REQUEST_KNOWLEDGE_IDENTITY_HINTS, handle_identity_hints)
    context.event_bus.subscribe_request(REQUEST_KNOWLEDGE_ENGRAM_CREATE, handle_create_engram)
    context.event_bus.subscribe_request(REQUEST_KNOWLEDGE_ENGRAM_UPDATE, handle_update_engram)
    context.event_bus.subscribe_request(REQUEST_KNOWLEDGE_ENGRAM_DELETE, handle_delete_engram)