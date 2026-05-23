from __future__ import annotations

from dataclasses import dataclass
import re
from typing import AsyncIterator
from uuid import uuid4

from app.core.events import EventBus
from app.interaction.application.service import InteractionService
from app.interaction.events import (
    InteractionMessageRecordRequest,
    InteractionRealtimeInput,
    InteractionSessionRequest,
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
        if _looks_like_internal_reasoning(content):
            # Avoid feeding leaked scaffolding back into the next prompt/history cycle.
            content = "[respuesta interna omitida por seguridad]"
        content = content.strip()
        if len(content) > 500:
            content = content[:500].rstrip() + "..."
        lines.append(f"{author}: {content}")
    return "\n".join(lines).strip()


def _packet(packet_type: str, *, session_id: str, **payload: object) -> dict[str, object]:
    return {"type": packet_type, "session_id": session_id, **payload}


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        normalized = item.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(item.strip())
    return ordered


def _dedupe_rule_lines(raw: str, *, max_lines: int = 10) -> str:
    seen: set[str] = set()
    cleaned: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        normalized = re.sub(r"^[-*\d\s.()]+", "", stripped)
        normalized = re.sub(r"\s+", " ", normalized).strip(" .:;,-").lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(stripped)
        if len(cleaned) >= max_lines:
            break
    return "\n".join(cleaned).strip()


def _compact_context_for_prompt(raw: str, *, max_lines: int = 8) -> str:
    kept: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if stripped.startswith("[") and stripped.endswith("]"):
            continue
        if lower.startswith("intent:") or lower.startswith("keywords:") or "score=" in lower:
            continue
        kept.append(stripped)
        if len(kept) >= max_lines:
            break
    return "\n".join(kept).strip()


def _is_simple_greeting(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    tokens = [token for token in normalized.split() if token]
    if not tokens:
        return False

    greeting_tokens = {
        "hola",
        "holi",
        "hello",
        "hi",
        "hey",
        "buenas",
        "buenos",
        "dias",
        "tardes",
        "noches",
        "que",
        "tal",
    }
    if len(tokens) > 4:
        return False
    non_greeting = [token for token in tokens if token not in greeting_tokens]
    return len(non_greeting) <= 1 and any(token in greeting_tokens for token in tokens)


def _is_identity_question(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()
    patterns = (
        r"\bquien\s+eres\b",
        r"\bsabes\s+quien\s+eres\b",
        r"\bcual\s+es\s+tu\s+nombre\b",
        r"\bcomo\s+te\s+llamas\b",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def _looks_like_internal_reasoning(text: str) -> bool:
    lower = text.lower()
    markers = (
        "analyze the request",
        "drafting the response",
        "specific instructions",
        "specific rule",
        "relevant engrams",
        "relevant knowledge",
        "context routing",
        "idea principal",
    )
    if any(marker in lower for marker in markers):
        return True
    if re.search(r"\d+\.\s+\*\*", text):
        return True
    return False


def _sanitize_generated_reply(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    if _looks_like_internal_reasoning(cleaned):
        return ""
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    filtered = [
        line
        for line in lines
        if not (line.startswith("[") and line.endswith("]"))
        and "score=" not in line.lower()
        and not line.lower().startswith(("intent:", "keywords:"))
    ]
    return "\n".join(filtered).strip() or ""


def _incremental_summary(previous: str, user_text: str, assistant_text: str, *, max_chars: int = 1400) -> str:
    blocks = [
        part.strip()
        for part in [
            previous.strip(),
            f"Usuario: {user_text.strip()}",
            f"Asistente: {assistant_text.strip()[:360]}",
        ]
        if part and part.strip()
    ]
    summary = "\n".join(blocks)
    if len(summary) <= max_chars:
        return summary
    return summary[-max_chars:]


def _coherence_score(main_idea: str, secondary_ideas: list[str], context_text: str, assistant_reply: str) -> float:
    targets = _extract_topics(" ".join([main_idea] + secondary_ideas + [context_text]), max_items=8)
    if not targets:
        return 0.5
    haystack = set(_extract_topics(assistant_reply, max_items=30))
    overlap = len([token for token in targets if token in haystack])
    ratio = overlap / max(1, len(targets))
    return round(max(0.0, min(1.0, ratio)), 3)


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
        history_messages = self.interaction_service.list_session_messages(
            InteractionSessionRequest(session_id=session_id, limit=history_limit)
        )
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
        history_messages = self.interaction_service.list_session_messages(
            InteractionSessionRequest(session_id=session_id, limit=input_data.history_limit)
        )
        history_text = _format_history(history_messages)
        stored_conditions = self.interaction_service.repository.get_session_conditions(session_id) or {}
        world_rules = (input_data.world_rules or str(stored_conditions.get("world_rules") or "")).strip()
        if input_data.world_rules.strip() and input_data.world_rules.strip() != str(stored_conditions.get("world_rules") or "").strip():
            self.interaction_service.repository.save_session_conditions(session_id, world_rules=input_data.world_rules)

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
                session_id=session_id,
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

        assistant_reply = self._compose_reply(input_data, context_preview, world_rules=world_rules)
        assistant_author = str(identity.get("name") or "assistant")
        assistant_message = self.interaction_service.record_message(
            InteractionMessageRecordRequest(
                author=assistant_author,
                content=assistant_reply,
                channel="assistant",
                session_id=session_id,
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

        topic_data = self._extract_turn_topics(input_data.content, assistant_reply, context_preview)
        self._persist_session_intelligence(
            session_id=session_id,
            turn_id=turn_id,
            user_input=input_data.content,
            assistant_reply=assistant_reply,
            topic_data=topic_data,
            context_preview=context_preview,
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

    def _extract_turn_topics(
        self,
        user_input: str,
        assistant_reply: str,
        context_preview: dict[str, object],
    ) -> dict[str, object]:
        context_pack = context_preview.get("context_pack", {}) if isinstance(context_preview, dict) else {}
        route_payload = context_pack.get("route", {}) if isinstance(context_pack, dict) else {}
        route_keywords = route_payload.get("keywords", []) if isinstance(route_payload, dict) else []
        candidates = _unique(
            _extract_topics(user_input, max_items=6)
            + [str(item).strip() for item in route_keywords if str(item).strip()]
            + _extract_topics(assistant_reply, max_items=6)
        )
        primary = candidates[0] if candidates else ""
        secondary = candidates[1:5] if len(candidates) > 1 else []
        return {"primary": primary, "secondary": secondary}

    def _persist_session_intelligence(
        self,
        *,
        session_id: str,
        turn_id: str,
        user_input: str,
        assistant_reply: str,
        topic_data: dict[str, object],
        context_preview: dict[str, object],
    ) -> None:
        repository = self.interaction_service.repository
        memory = repository.get_session_memory(session_id) or {}
        previous_summary = str(memory.get("summary_text") or "")

        primary_topic = str(topic_data.get("primary") or "")
        secondary_topics = [str(item).strip() for item in list(topic_data.get("secondary") or []) if str(item).strip()]
        context_text = str(context_preview.get("context_text") or "")
        coherence = _coherence_score(primary_topic, secondary_topics, context_text, assistant_reply)
        summary_text = _incremental_summary(previous_summary, user_input, assistant_reply)

        repository.save_session_memory(
            session_id,
            summary_text=summary_text,
            sliding_window_size=20,
            last_turn_id=turn_id,
            coherence_score=coherence,
        )

        graph = repository.get_session_topic_graph(session_id) or {}
        previous_primary = str(graph.get("primary_topic") or "")
        existing_secondary = [str(item).strip() for item in list(graph.get("secondary_topics") or []) if str(item).strip()]
        merged_secondary = _unique(existing_secondary + secondary_topics)
        topic_states = {str(k): str(v) for k, v in dict(graph.get("topic_states") or {}).items()}
        if primary_topic:
            topic_states[primary_topic] = "active"
        for topic in merged_secondary:
            topic_states.setdefault(topic, "tracked")

        edges = [dict(edge) for edge in list(graph.get("edges") or []) if isinstance(edge, dict)]
        if previous_primary and primary_topic and previous_primary != primary_topic:
            edges.append({"source": previous_primary, "target": primary_topic, "relation": "shift"})
        for topic in secondary_topics:
            if primary_topic and topic != primary_topic:
                edges.append({"source": primary_topic, "target": topic, "relation": "supports"})

        repository.save_session_topic_graph(
            session_id,
            primary_topic=primary_topic or previous_primary,
            secondary_topics=merged_secondary,
            topic_states=topic_states,
            edges=edges[-40:],
        )

        trace = context_preview.get("context_pack", {}).get("trace", {}) if isinstance(context_preview, dict) else {}
        repository.save_turn_metric(
            turn_id=turn_id,
            session_id=session_id,
            user_input=user_input,
            assistant_reply=assistant_reply,
            primary_topic=primary_topic,
            secondary_topics=secondary_topics,
            coherence_score=coherence,
            context_trace=trace if isinstance(trace, dict) else {},
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

    def _compose_reply(
        self,
        input_data: InteractionRealtimeInput,
        context_preview: dict[str, object],
        *,
        world_rules: str = "",
    ) -> str:
        identity = context_preview.get("identity", {})
        identity_name = str(identity.get("name") or "assistant")
        behavior_prompt = _dedupe_rule_lines(str(identity.get("behavior_prompt") or ""), max_lines=8)
        meta_rule = _dedupe_rule_lines(str(identity.get("meta_rule") or ""), max_lines=8)
        intellectual_profile = str(identity.get("intellectual_profile") or "").strip()
        context_pack = context_preview.get("context_pack", {})
        knowledge_matches = list(context_pack.get("knowledge_matches", []))
        engram_matches = list(context_pack.get("engram_matches", []))
        context_text = str(context_preview.get("context_text") or "").strip()
        compact_context_text = _compact_context_for_prompt(context_text)
        world_rules = _dedupe_rule_lines(world_rules, max_lines=10)
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

        if _is_simple_greeting(input_data.content):
            return f"Hola, soy {identity_name}. En que te ayudo hoy?"
        if _is_identity_question(input_data.content):
            return f"Si, soy {identity_name}, tu asistente activo en este chat. Puedo ayudarte con dudas tecnicas, RAG y tareas operativas."

        if knowledge_matches:
            primary_label = str(knowledge_matches[0].get("label") or main_idea).strip() if isinstance(knowledge_matches[0], dict) else main_idea
            fallback_reply = (
                f"Entendido. Soy {identity_name}. Segun el contexto recuperado, el punto principal es '{primary_label}'. "
                "Si quieres, te lo explico en breve o lo aplicamos a un caso concreto."
            )
        else:
            fallback_reply = (
                f"Soy {identity_name}. Te leo: '{input_data.content.strip()}'. "
                "Dime que necesitas y te respondo directo y en corto."
            )

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
        if world_rules:
            prompt_sections.append(f"Reglas del mundo activas para esta sesion:\n{world_rules}")
        if compact_context_text:
            prompt_sections.append(f"Contexto recuperado:\n{compact_context_text}")
        if knowledge_matches:
            prompt_sections.append(
                "Coincidencias relevantes:\n" + "\n".join(
                    f"- {str(match.get('label') or 'contexto')}: {str(match.get('excerpt') or '').strip()}"
                    for match in knowledge_matches[:4]
                )
            )
        prompt_sections.append(
            "Responde al usuario de forma directa, breve y util en espanol."
        )
        prompt_sections.append(
            "No muestres analisis interno, listas de planificacion, ni encabezados tecnicos como "
            "[CONTEXT ROUTING], [RELEVANT KNOWLEDGE] o [RELEVANT ENGRAMS]."
        )
        prompt_sections.append("Responde como el asistente activo y no menciones detalles internos del runtime.")
        prompt = "\n\n".join(section for section in prompt_sections if section.strip())

        identity_id = str(identity.get("id") or "").strip().upper()
        has_custom_engram = identity_id not in {"", "DEFAULT", "SETUP", "ERR"}

        # If no custom engram is configured, use conservative test defaults.
        default_temperature = 0.35 if has_custom_engram else 0.2
        default_top_p = 1.0 if has_custom_engram else 0.9
        default_max_tokens = 768 if has_custom_engram else 512

        temperature = default_temperature
        try:
            temperature = float(identity.get("resolved_temperature") or identity.get("temperatura_base") or default_temperature)
        except (TypeError, ValueError):
            temperature = default_temperature
        temperature = max(0.0, min(2.0, temperature))

        top_p = default_top_p
        try:
            top_p = float(identity.get("resolved_top_p") or identity.get("top_p_base") or default_top_p)
        except (TypeError, ValueError):
            top_p = default_top_p
        top_p = max(0.0, min(1.0, top_p))

        max_tokens = default_max_tokens
        try:
            max_tokens = int(identity.get("resolved_max_tokens") or identity.get("max_tokens_respuesta") or default_max_tokens)
        except (TypeError, ValueError):
            max_tokens = default_max_tokens
        max_tokens = max(128, min(2048, max_tokens))

        try:
            generated = self.event_bus.request(
                REQUEST_MODEL_TEXT_GENERATION,
                ModelTextGenerationRequest(prompt=prompt, temperature=temperature, top_p=top_p, max_tokens=max_tokens),
                source_module="interaction.application.realtime",
            )
            content = str(generated.get("content") or "").strip() if isinstance(generated, dict) else ""
            sanitized = _sanitize_generated_reply(content)
            if isinstance(generated, dict) and generated.get("ok") and sanitized:
                return sanitized
        except Exception:
            pass

        return fallback_reply