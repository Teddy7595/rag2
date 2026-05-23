from __future__ import annotations

from dataclasses import dataclass
import re
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
from app.models.events import ModelTextGenerationRequest, REQUEST_MODEL_TEXT_GENERATION


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


def _extract_topics(text: str, *, max_items: int = 5) -> list[str]:
    stopwords = {
        "de",
        "la",
        "el",
        "los",
        "las",
        "y",
        "o",
        "con",
        "sin",
        "para",
        "por",
        "del",
        "que",
        "una",
        "uno",
        "unos",
        "unas",
        "como",
        "esto",
        "esta",
        "estas",
        "este",
        "estos",
        "sobre",
        "pero",
        "donde",
        "cuando",
        "quien",
        "cual",
        "porque",
        "ser",
        "estar",
        "hacer",
        "tener",
    }
    tokens = re.findall(r"[a-z0-9áéíóúñ]{3,}", text.lower())
    ranked: list[str] = []
    for token in tokens:
        if token in stopwords or token in ranked:
            continue
        ranked.append(token)
        if len(ranked) >= max_items:
            break
    return ranked


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
        behavior_prompt = str(identity.get("behavior_prompt") or "").strip()
        meta_rule = str(identity.get("meta_rule") or "").strip()
        intellectual_profile = str(identity.get("intellectual_profile") or "").strip()
        context_pack = context_preview.get("context_pack", {})
        knowledge_matches = list(context_pack.get("knowledge_matches", []))
        engram_matches = list(context_pack.get("engram_matches", []))
        context_text = str(context_preview.get("context_text") or "").strip()
        route_payload = context_pack.get("route", {}) if isinstance(context_pack, dict) else {}
        route_keywords = route_payload.get("keywords", []) if isinstance(route_payload, dict) else []

        main_idea = ""
        secondary_ideas: list[str] = []

        if knowledge_matches:
            first_match = knowledge_matches[0] if isinstance(knowledge_matches[0], dict) else {}
            main_idea = str(first_match.get("label") or "").strip()
            for match in knowledge_matches[1:4]:
                if isinstance(match, dict):
                    label = str(match.get("label") or "").strip()
                    if label and label != main_idea and label not in secondary_ideas:
                        secondary_ideas.append(label)

        if not main_idea:
            message_topics = _extract_topics(input_data.content)
            route_topics = [str(item).strip() for item in route_keywords if str(item).strip()]
            merged_topics = [topic for topic in message_topics + route_topics if topic]
            if merged_topics:
                main_idea = merged_topics[0]
                for topic in merged_topics[1:4]:
                    if topic != main_idea and topic not in secondary_ideas:
                        secondary_ideas.append(topic)

        if not main_idea:
            main_idea = input_data.content.strip()[:80]

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

        lines.append(f"Idea principal detectada: {main_idea}")
        if secondary_ideas:
            lines.append("Ideas secundarias detectadas: " + ", ".join(secondary_ideas))

        lines.append("Siguiente paso: sigo el contexto recuperado y mantengo el historial persistente.")
        fallback_reply = "\n".join(lines).strip()

        prompt_sections = [
            f"Identidad activa: {identity_name}.",
            "Responde en espanol, de forma clara y concisa.",
            f"Mensaje del usuario: {input_data.content.strip()}",
            f"Idea principal: {main_idea}",
        ]
        if secondary_ideas:
            prompt_sections.append("Ideas secundarias: " + ", ".join(secondary_ideas))
        if intellectual_profile:
            prompt_sections.append(f"Perfil intelectual del engrama: {intellectual_profile}")
        if behavior_prompt:
            prompt_sections.append(f"Instruccion de comportamiento del engrama: {behavior_prompt}")
        if meta_rule:
            prompt_sections.append(f"Meta-regla del engrama: {meta_rule}")
        if context_text:
            prompt_sections.append(f"Contexto recuperado:\n{context_text}")
        if knowledge_matches:
            prompt_sections.append(
                "Coincidencias relevantes:\n" + "\n".join(
                    f"- {str(match.get('label') or 'contexto')}: {str(match.get('excerpt') or '').strip()}"
                    for match in knowledge_matches[:4]
                )
            )
        prompt_sections.append(
            "Estructura la respuesta en este orden: "
            "1) idea principal, 2) ideas secundarias conectadas, 3) respuesta integrada, 4) siguiente accion sugerida."
        )
        prompt_sections.append("Responde como el asistente activo y no menciones detalles internos del runtime.")
        prompt = "\n\n".join(section for section in prompt_sections if section.strip())

        temperature = 0.35
        try:
            temperature = float(identity.get("resolved_temperature") or identity.get("temperatura_base") or 0.35)
        except (TypeError, ValueError):
            temperature = 0.35
        temperature = max(0.0, min(2.0, temperature))

        max_tokens = 768
        try:
            max_tokens = int(identity.get("resolved_max_tokens") or identity.get("max_tokens_respuesta") or 768)
        except (TypeError, ValueError):
            max_tokens = 768
        max_tokens = max(128, min(2048, max_tokens))

        try:
            generated = self.event_bus.request(
                REQUEST_MODEL_TEXT_GENERATION,
                ModelTextGenerationRequest(prompt=prompt, temperature=temperature, max_tokens=max_tokens),
                source_module="interaction.application.realtime",
            )
            content = str(generated.get("content") or "").strip() if isinstance(generated, dict) else ""
            if isinstance(generated, dict) and generated.get("ok") and content:
                return content
        except Exception:
            pass

        return fallback_reply