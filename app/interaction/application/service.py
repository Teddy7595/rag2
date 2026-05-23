from __future__ import annotations

from app.core.events import EventBus
from app.interaction.domain import ConversationMessage
from app.interaction.events import (
    InteractionHistoryRequest,
    InteractionMessageRecordRequest,
    InteractionSummaryRequest,
    PUBLISH_INTERACTION_MESSAGE_RECORDED,
)
from app.interaction.application.ports import InteractionMessageRepositoryPort
from app.knowledge.events import REQUEST_KNOWLEDGE_OVERVIEW, KnowledgeOverviewRequest


class InteractionService:
    def __init__(self, event_bus: EventBus, repository: InteractionMessageRepositoryPort) -> None:
        self.event_bus = event_bus
        self.repository = repository

    def summary(self, request: InteractionSummaryRequest) -> dict[str, object]:
        recent_messages = self.list_messages(InteractionHistoryRequest(limit=request.limit))
        knowledge_overview = self.event_bus.request(
            REQUEST_KNOWLEDGE_OVERVIEW,
            KnowledgeOverviewRequest(limit=request.limit),
            source_module="interaction.application.service",
        )
        return {
            "message_count": self.repository.count(),
            "recent_messages": recent_messages,
            "knowledge_overview": knowledge_overview,
            "channel_counts": self.repository.channel_counts(),
        }

    def list_messages(self, request: InteractionHistoryRequest) -> list[dict[str, object]]:
        messages = self.repository.list_recent(request.limit)
        return [message.as_dict() for message in messages]

    def record_message(self, request: InteractionMessageRecordRequest) -> dict[str, object]:
        message = ConversationMessage(
            author=request.author,
            content=request.content,
            channel=request.channel,
        )
        persisted = self.repository.save(message)
        payload = persisted.as_dict()
        self.event_bus.publish(
            PUBLISH_INTERACTION_MESSAGE_RECORDED,
            payload,
            source_module="interaction.application.service",
            metadata={"author": message.author, "channel": message.channel},
        )
        return payload