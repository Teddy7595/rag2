from fastapi import FastAPI

from app.core.app_context import get_app_context_from_app
from app.core.events import EventEnvelope
from app.knowledge.application import KnowledgeService
from app.knowledge.events import KnowledgeItemCreateRequest, KnowledgeItemsRequest, KnowledgeOverviewRequest, REQUEST_KNOWLEDGE_ITEM_CREATE, REQUEST_KNOWLEDGE_ITEMS, REQUEST_KNOWLEDGE_OVERVIEW


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

    context.event_bus.subscribe_request(REQUEST_KNOWLEDGE_OVERVIEW, handle_overview)
    context.event_bus.subscribe_request(REQUEST_KNOWLEDGE_ITEMS, handle_items)
    context.event_bus.subscribe_request(REQUEST_KNOWLEDGE_ITEM_CREATE, handle_create)