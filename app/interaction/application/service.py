from __future__ import annotations

from typing import Callable

from app.core.events import EventBus
from app.interaction.domain import ConversationMessage
from app.interaction.domain import IdeaClip
from app.interaction.events import (
    IdeaClipDeleteRequest,
    IdeaClipListRequest,
    IdeaClipSaveRequest,
    InteractionContextTraceRequest,
    InteractionHistoryRequest,
    InteractionMessageActionRequest,
    InteractionMessageRecordRequest,
    InteractionDeletedSessionsRequest,
    InteractionSessionsRequest,
    InteractionSessionDeleteRequest,
    InteractionSessionRewindRequest,
    InteractionSessionRequest,
    InteractionSessionConditionsRequest,
    InteractionSummaryRequest,
    PUBLISH_INTERACTION_MESSAGE_RECORDED,
)
from app.interaction.application.ports import InteractionMessageRepositoryPort
from app.knowledge.events import (
    REQUEST_KNOWLEDGE_ITEM_CREATE,
    REQUEST_KNOWLEDGE_OVERVIEW,
    KnowledgeItemCreateRequest,
    KnowledgeOverviewRequest,
)


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

    def list_sessions(self, request: InteractionSessionsRequest) -> list[dict[str, object]]:
        return self.repository.list_sessions(limit=request.limit)

    def list_deleted_sessions(self, request: InteractionDeletedSessionsRequest) -> list[dict[str, object]]:
        return self.repository.list_deleted_sessions(limit=request.limit)

    def list_session_messages(self, request: InteractionSessionRequest) -> list[dict[str, object]]:
        messages = self.repository.list_session_messages(request.session_id, request.limit)
        return [message.as_dict() for message in messages]

    def record_message(self, request: InteractionMessageRecordRequest) -> dict[str, object]:
        message = ConversationMessage(
            author=request.author,
            content=request.content,
            channel=request.channel,
            session_id=request.session_id,
            reply_to_message_id=request.reply_to_message_id,
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

    def record_message_nowait(
        self, request: InteractionMessageRecordRequest
    ) -> tuple[dict[str, object], Callable[[], None]]:
        """Build the message entity and return its dict immediately.

        The second return value is a zero-argument callable that performs the
        actual repository write and event publish.  The caller is responsible
        for executing it in a background thread so the hot-path is not blocked
        by I/O.
        """
        message = ConversationMessage(
            author=request.author,
            content=request.content,
            channel=request.channel,
            session_id=request.session_id,
            reply_to_message_id=request.reply_to_message_id,
        )
        payload = message.as_dict()

        def _persist() -> None:
            try:
                persisted = self.repository.save(message)
                self.event_bus.publish(
                    PUBLISH_INTERACTION_MESSAGE_RECORDED,
                    persisted.as_dict(),
                    source_module="interaction.application.service",
                    metadata={"author": message.author, "channel": message.channel},
                )
            except Exception:
                pass  # background failures are non-fatal; message dict already returned

        return payload, _persist

    def hide_message(self, request: InteractionMessageActionRequest) -> dict[str, object]:
        message = self.repository.hide_message(request.message_id)
        return {
            "ok": message is not None,
            "action": "hide",
            "message": message.as_dict() if message else None,
        }

    def memorize_message(self, request: InteractionMessageActionRequest) -> dict[str, object]:
        message = self.repository.get_by_id(request.message_id)
        if not message:
            return {"ok": False, "action": "memorize", "reason": "message_not_found"}

        title = f"Memoria chat {message.id[:8]}"
        tags = ["chat", "memorized", message.channel]
        if message.session_id:
            tags.append(f"session:{message.session_id}")

        created = self.event_bus.request(
            REQUEST_KNOWLEDGE_ITEM_CREATE,
            KnowledgeItemCreateRequest(title=title, content=message.content, tags=tags),
            source_module="interaction.application.service",
        )
        return {
            "ok": True,
            "action": "memorize",
            "message": message.as_dict(),
            "knowledge": created,
        }

    def rewind_session(self, request: InteractionSessionRewindRequest) -> dict[str, object]:
        return self.repository.rewind_session(request.session_id, request.message_id)

    def delete_session(self, request: InteractionSessionDeleteRequest) -> dict[str, object]:
        return self.repository.delete_session(request.session_id, hard_delete=request.hard_delete)

    def restore_session(self, request: InteractionSessionDeleteRequest) -> dict[str, object]:
        return self.repository.restore_session(request.session_id)

    def context_traces(self, request: InteractionContextTraceRequest) -> list[dict[str, object]]:
        return self.repository.list_context_traces(
            trace_id=request.trace_id,
            session_id=request.session_id,
            trigger=request.trigger,
            limit=request.limit,
        )

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

    # ------------------------------------------------------------------
    # IdeaClip (librito de ideas)
    # ------------------------------------------------------------------

    def save_idea_clip(self, request: IdeaClipSaveRequest) -> dict[str, object]:
        clip = IdeaClip(
            content=request.content,
            label=request.label,
            source_message_id=request.source_message_id,
            session_id=request.session_id,
            tags=list(request.tags),
        )
        persisted = self.repository.save_idea_clip(clip)
        return persisted.as_dict()

    def list_idea_clips(self, request: IdeaClipListRequest) -> list[dict[str, object]]:
        clips = self.repository.list_idea_clips(limit=request.limit, session_id=request.session_id)
        return [c.as_dict() for c in clips]

    def delete_idea_clip(self, request: IdeaClipDeleteRequest) -> dict[str, object]:
        ok = self.repository.delete_idea_clip(request.clip_id)
        return {"ok": ok, "clip_id": request.clip_id}