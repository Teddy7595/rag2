from __future__ import annotations

from app.core.events import EventBus
from app.interaction.domain import ConversationMessage
from app.interaction.events import (
    InteractionHistoryRequest,
    InteractionMessageRecordRequest,
    InteractionSessionRequest,
    InteractionSessionConditionsRequest,
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
            session_id=request.session_id,
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

    def session_memory(self, request: InteractionSessionRequest) -> dict[str, object]:
        return self.repository.get_session_memory(request.session_id) or {
            "session_id": request.session_id,
            "summary_text": "",
            "sliding_window_size": max(1, request.limit),
            "last_turn_id": None,
            "coherence_score": 0.0,
            "updated_at": None,
        }

    def session_topic_graph(self, request: InteractionSessionRequest) -> dict[str, object]:
        return self.repository.get_session_topic_graph(request.session_id) or {
            "session_id": request.session_id,
            "primary_topic": "",
            "secondary_topics": [],
            "topic_states": {},
            "edges": [],
            "updated_at": None,
        }

    def turn_metrics(self, request: InteractionSessionRequest) -> list[dict[str, object]]:
        return self.repository.list_turn_metrics(request.session_id, limit=request.limit)

    def session_conditions(self, request: InteractionSessionRequest) -> dict[str, object]:
        return self.repository.get_session_conditions(request.session_id) or {
            "session_id": request.session_id,
            "world_rules": "",
            "updated_at": None,
        }

    def set_session_conditions(self, request: InteractionSessionConditionsRequest) -> dict[str, object]:
        return self.repository.save_session_conditions(request.session_id, world_rules=request.world_rules)