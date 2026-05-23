from __future__ import annotations

from app.core.events import EventBus
from app.knowledge.application.ports import KnowledgeRepositoryPort
from app.knowledge.domain import KnowledgeEntry
from app.knowledge.events import (
    KnowledgeItemCreateRequest,
    KnowledgeItemsRequest,
    KnowledgeOverviewRequest,
    PUBLISH_KNOWLEDGE_ITEM_CREATED,
)


class KnowledgeService:
    def __init__(self, repository: KnowledgeRepositoryPort, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    def overview(self, request: KnowledgeOverviewRequest) -> dict[str, object]:
        items = self.list_items(KnowledgeItemsRequest(limit=request.limit))
        titles = [item["title"] for item in items] if request.include_titles else []
        return {
            "item_count": self.repository.count(),
            "recent_items": items,
            "titles": titles,
        }

    def list_items(self, request: KnowledgeItemsRequest) -> list[dict[str, object]]:
        if request.limit <= 0:
            return []
        items = self.repository.list_recent(limit=request.limit)
        return [item.as_dict() for item in items]

    def create_item(self, request: KnowledgeItemCreateRequest) -> dict[str, object]:
        entry = KnowledgeEntry(title=request.title, content=request.content, tags=list(request.tags))
        saved_entry = self.repository.save(entry)
        payload = saved_entry.as_dict()
        self.event_bus.publish(
            PUBLISH_KNOWLEDGE_ITEM_CREATED,
            payload,
            source_module="knowledge.application.service",
            metadata={"tags": payload["tags"]},
        )
        return payload