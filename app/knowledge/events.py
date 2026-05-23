from __future__ import annotations

from dataclasses import dataclass

from app.core.events import EventChannel, EventKind, EventSpec


@dataclass(frozen=True)
class KnowledgeOverviewRequest:
    limit: int = 5
    include_titles: bool = True


@dataclass(frozen=True)
class KnowledgeItemsRequest:
    limit: int = 20


@dataclass(frozen=True)
class KnowledgeItemCreateRequest:
    title: str
    content: str
    tags: tuple[str, ...] = ()


REQUEST_KNOWLEDGE_OVERVIEW = EventSpec[KnowledgeOverviewRequest, dict](
    name="knowledge.overview.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=KnowledgeOverviewRequest,
    output_type=dict,
)

REQUEST_KNOWLEDGE_ITEMS = EventSpec[KnowledgeItemsRequest, list](
    name="knowledge.items.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=KnowledgeItemsRequest,
    output_type=list,
)

REQUEST_KNOWLEDGE_ITEM_CREATE = EventSpec[KnowledgeItemCreateRequest, dict](
    name="knowledge.item.create.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=KnowledgeItemCreateRequest,
    output_type=dict,
)

PUBLISH_KNOWLEDGE_ITEM_CREATED = EventSpec[dict, dict](
    name="knowledge.item.created",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)


__all__ = [
    "KnowledgeItemCreateRequest",
    "KnowledgeItemsRequest",
    "KnowledgeOverviewRequest",
    "PUBLISH_KNOWLEDGE_ITEM_CREATED",
    "REQUEST_KNOWLEDGE_ITEM_CREATE",
    "REQUEST_KNOWLEDGE_ITEMS",
    "REQUEST_KNOWLEDGE_OVERVIEW",
]