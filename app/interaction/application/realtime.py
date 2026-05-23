from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator
from uuid import uuid4

from app.core.events import EventBus
from app.interaction.application.service import InteractionService
from app.interaction.events import (
    InteractionHistoryRequest,
    InteractionMessageRecordRequest,
    InteractionRealtimeInput,
    PUBLISH_INTERACTION_REALTIME_MESSAGE_RECEIVED,
    PUBLISH_INTERACTION_REALTIME_REPLY_STREAMED,
    PUBLISH_INTERACTION_REALTIME_SESSION_ENDED,
    PUBLISH_INTERACTION_REALTIME_SESSION_STARTED,
    PUBLISH_INTERACTION_REALTIME_TURN_COMPLETED,
)
from app.knowledge.events import ContextBuildRequest, CurrentIdentityRequest, REQUEST_KNOWLEDGE_CONTEXT_PROMPT, REQUEST_KNOWLEDGE_CURRENT_IDENTITY


def _message_role(author: str, channel: str) -> str:
    if author.lower() == "user" or channel == "chat":
        return "user"
    return "assistant"


def _format_history(messages: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for message in messages:
        author = str(message.get("author") or "unknown")
        content = str(message.get("content") or "")
        lines.append(f"{author}: {content}")
    return "\n".join(lines).strip()


def _packet(packet_type: str, *, session_id: str, **payload: object) -> dict[str, object]:
    return {"type": packet_type, "session_id": session_id, **payload}


@dataclass(frozen=True)
class RealtimeTurnResult:
    session_id: str
    turn_id: str
    identity: dict[str, object]
    context_preview: dict[str, object]
    user_message: dict[str, object]
    assistant_message: dict[str, object]
    assistant_reply: str
    history_messages: list[dict[str, object]]


@dataclass(frozen=True)
class RealtimeSessionSnapshot:
    session_id: str
    identity: dict[str, object]
    history_messages: list[dict[str, object]]

    def to_packets(self) -> list[dict[str, object]]:
        packets: list[dict[str, object]] = [
            _packet(
                "session_started",
                session_id=self.session_id,
                identity=self.identity,
                history_count=len(self.history_messages),
            )
        ]

        for message in self.history_messages:
            packets.append(
                _packet(
                    "history_message",
                    session_id=self.session_id,
                    message=message,
                    role=_message_role(str(message.get("author") or ""), str(message.get("channel") or "")),
                )
            )

        packets.append(
            _packet(
                "meta_update",
                session_id=self.session_id,
                identity=self.identity,
                name=self.identity.get("name"),
                avatar=self.identity.get("avatar"),
                color=self.identity.get("color_hex"),
            )
        )
        packets.append(
            _packet(
                "welcome",
                session_id=self.session_id,
                content=f"Conectado como {self.identity.get('name')}. El chat realtime está listo.",
            )
        )
        return packets


class RealtimeChatService:
    def __init__(self, event_bus: EventBus, interaction_service: InteractionService) -> None:
        self.event_bus = event_bus
        self.interaction_service = interaction_service

    def open_session(self, session_id: str | None = None, *, history_limit: int = 20) -> RealtimeSessionSnapshot:
        session_id = session_id or str(uuid4())
        identity = self._current_identity()
        history_messages = self.interaction_service.list_messages(InteractionHistoryRequest(limit=history_limit))
        snapshot = RealtimeSessionSnapshot(session_id=session_id, identity=identity, history_messages=history_messages)
        self.event_bus.publish(
            PUBLISH_INTERACTION_REALTIME_SESSION_STARTED,
            {
                "session_id": session_id,
                "identity": identity,
                "history_count": len(history_messages),
            },
            source_module="interaction.application.realtime",
            metadata={"session_id": session_id, "history_count": len(history_messages)},
        )
        return snapshot

    async def stream_turn(
        self,
        input_data: InteractionRealtimeInput,
        *,
        session_id: str | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        session_id = session_id or str(uuid4())
        turn_result = self.build_turn(session_id, input_data)

        yield _packet(
            "turn_started",
            session_id=session_id,
            turn_id=turn_result.turn_id,
            identity=turn_result.identity,
            context=turn_result.context_preview,
        )

        for token in turn_result.assistant_reply.split():
            yield _packet(
                "assistant_token",
                session_id=session_id,
                turn_id=turn_result.turn_id,
                token=token,
            )

        yield _packet(
            "assistant_message",
            session_id=session_id,
            turn_id=turn_result.turn_id,
            message=turn_result.assistant_message,
        )
        yield _packet(
            "turn_complete",
            session_id=session_id,
            turn_id=turn_result.turn_id,
            assistant_message=turn_result.assistant_message,
            history_count=len(turn_result.history_messages),
        )

    def build_turn(self, session_id: str, input_data: InteractionRealtimeInput) -> RealtimeTurnResult:
        turn_id = str(uuid4())
        history_messages = self.interaction_service.list_messages(InteractionHistoryRequest(limit=input_data.history_limit))
        history_text = _format_history(history_messages)

        context_preview = self.event_bus.request(
            REQUEST_KNOWLEDGE_CONTEXT_PROMPT,
            ContextBuildRequest(
                raw_text=input_data.content,
                limit=input_data.context_limit,
                identity_id=input_data.identity_id,
                history=history_text,
            ),
            source_module="interaction.application.realtime",
        )

        identity = context_preview["identity"]
        user_message = self.interaction_service.record_message(
            InteractionMessageRecordRequest(
                author=input_data.author,
                content=input_data.content,
                channel=input_data.channel,
            )
        )
        self.event_bus.publish(
            PUBLISH_INTERACTION_REALTIME_MESSAGE_RECEIVED,
            {
                "session_id": session_id,
                "turn_id": turn_id,
                "user_message": user_message,
                "identity": identity,
            },
            source_module="interaction.application.realtime",
            metadata={"session_id": session_id, "turn_id": turn_id, "author": user_message.get("author")},
        )

        assistant_reply = self._compose_reply(input_data, context_preview)
        assistant_author = str(identity.get("name") or "assistant")
        assistant_message = self.interaction_service.record_message(
            InteractionMessageRecordRequest(
                author=assistant_author,
                content=assistant_reply,
                channel="assistant",
            )
        )
        self.event_bus.publish(
            PUBLISH_INTERACTION_REALTIME_REPLY_STREAMED,
            {
                "session_id": session_id,
                "turn_id": turn_id,
                "assistant_message": assistant_message,
                "identity": identity,
            },
            source_module="interaction.application.realtime",
            metadata={"session_id": session_id, "turn_id": turn_id, "assistant_author": assistant_author},
        )

        self.event_bus.publish(
            PUBLISH_INTERACTION_REALTIME_TURN_COMPLETED,
            {
                "session_id": session_id,
                "turn_id": turn_id,
                "identity": identity,
                "user_message": user_message,
                "assistant_message": assistant_message,
                "context_trace": context_preview.get("context_pack", {}).get("trace", {}),
            },
            source_module="interaction.application.realtime",
            metadata={
                "session_id": session_id,
                "turn_id": turn_id,
                "assistant_author": assistant_author,
            },
        )

        return RealtimeTurnResult(
            session_id=session_id,
            turn_id=turn_id,
            identity=identity,
            context_preview=context_preview,
            user_message=user_message,
            assistant_message=assistant_message,
            assistant_reply=assistant_reply,
            history_messages=history_messages,
        )

    def close_session(self, session_id: str, *, reason: str = "client_disconnect") -> None:
        self.event_bus.publish(
            PUBLISH_INTERACTION_REALTIME_SESSION_ENDED,
            {"session_id": session_id, "reason": reason},
            source_module="interaction.application.realtime",
            metadata={"session_id": session_id, "reason": reason},
        )

    def _current_identity(self) -> dict[str, object]:
        return self.event_bus.request(
            REQUEST_KNOWLEDGE_CURRENT_IDENTITY,
            CurrentIdentityRequest(),
            source_module="interaction.application.realtime",
        )

    def _compose_reply(self, input_data: InteractionRealtimeInput, context_preview: dict[str, object]) -> str:
        identity = context_preview.get("identity", {})
        identity_name = str(identity.get("name") or "assistant")
        context_pack = context_preview.get("context_pack", {})
        knowledge_matches = list(context_pack.get("knowledge_matches", []))
        engram_matches = list(context_pack.get("engram_matches", []))
        context_text = str(context_preview.get("context_text") or "").strip()

        lines: list[str] = [f"{identity_name}: recibí '{input_data.content.strip()}'."]

        if knowledge_matches:
            lines.append("Contexto recuperado:")
            for match in knowledge_matches[:3]:
                label = str(match.get("label") or "contexto")
                excerpt = str(match.get("excerpt") or "").strip()
                if excerpt:
                    lines.append(f"- {label}: {excerpt}")
                else:
                    lines.append(f"- {label}")
        else:
            lines.append("No encontré contexto relevante todavía.")

        if engram_matches:
            lines.append("Identidad activa:")
            for match in engram_matches[:2]:
                label = str(match.get("label") or identity_name)
                lines.append(f"- {label}")

        if context_text:
            lines.append("Resumen de contexto:")
            lines.append(context_text)

        lines.append("Siguiente paso: sigo el contexto recuperado y mantengo el historial persistente.")
        return "\n".join(lines).strip()