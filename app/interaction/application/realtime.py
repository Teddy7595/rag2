from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import re
import time
from typing import AsyncIterator, Callable
from uuid import uuid4

from app.core.events import EventBus
from app.interaction.application.governance import (
    build_turn_policy,
    compact_context_for_prompt,
    dedupe_rule_lines,
    detect_repetition,
    evaluate_immersive_response,
    instruction_echo_prefix_detected,
    looks_like_internal_reasoning,
    sanitize_generated_reply,
    sanitize_history_content,
)
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
from app.knowledge.application.embedding_runtime import SemanticEmbeddingRuntime
from app.models.runtime_service import LocalInferenceService
from app.models.events import (
    ModelGenerationDefaultsRequest,
    ModelTextGenerationRequest,
    REQUEST_MODEL_GENERATION_DEFAULTS,
    REQUEST_MODEL_TEXT_GENERATION,
)


logger = logging.getLogger(__name__)


def _message_role(author: str, channel: str) -> str:
    if author.lower() == "user" or channel == "chat":
        return "user"
    return "assistant"


def _format_history(messages: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for message in messages:
        author = str(message.get("author") or "unknown")
        content = sanitize_history_content(str(message.get("content") or ""))
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


def _normalize_reply_for_compare(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9áéíóúñ\s]", "", text.lower())).strip()


def _recent_assistant_replies(messages: list[dict[str, object]], *, limit: int = 4) -> list[str]:
    replies: list[str] = []
    for message in reversed(messages):
        channel = str(message.get("channel") or "")
        author = str(message.get("author") or "")
        if channel == "assistant" or author.lower() != "user":
            content = str(message.get("content") or "").strip()
            if content:
                replies.append(content)
            if len(replies) >= limit:
                break
    return replies


def _looks_mostly_english(text: str) -> bool:
    lowered = re.sub(r"\s+", " ", text.lower()).strip()
    if not lowered:
        return False

    english_tokens = {
        "the",
        "and",
        "you",
        "your",
        "are",
        "is",
        "with",
        "for",
        "this",
        "that",
        "can",
        "will",
        "from",
        "about",
        "please",
        "answer",
        "response",
    }
    spanish_tokens = {
        "el",
        "la",
        "los",
        "las",
        "que",
        "como",
        "para",
        "con",
        "sin",
        "por",
        "respuesta",
        "usuario",
        "puedo",
        "quiero",
        "estoy",
        "eres",
        "soy",
    }
    words = re.findall(r"[a-záéíóúñ]{2,}", lowered)
    if len(words) < 6:
        return False

    eng_hits = sum(1 for word in words if word in english_tokens)
    spa_hits = sum(1 for word in words if word in spanish_tokens)
    has_spanish_chars = bool(re.search(r"[áéíóúñ¿¡]", lowered))

    return eng_hits >= 3 and eng_hits > spa_hits and not has_spanish_chars


def _choose_conversational_fallback(user_text: str, identity_name: str, *, repeat_variant: bool = False) -> str:
    normalized = re.sub(r"\s+", " ", user_text.lower()).strip()
    if re.search(r"\b(hola|buenas|hey|hi|hello|que tal)\b", normalized):
        return f"Hola, soy {identity_name}. Te leo. Si quieres, empezamos por lo que necesitas ahora mismo y lo resolvemos en corto."

    if re.search(r"\b(resume|explica|dime|ayuda|quiero|necesito|puedes|podrias|podrías)\b", normalized):
        return (
            f"Soy {identity_name}. Entendido: {user_text.strip()[:120]}. "
            "Te respondo directo y en claro a continuacion."
        )

    tone_index = sum(ord(char) for char in normalized) % 3 if normalized else 0
    variants = [
        f"Soy {identity_name}. Te respondo claro y natural, sin rodeos.",
        f"Soy {identity_name}. Vamos al punto, con una respuesta concreta.",
        f"Soy {identity_name}. Te doy una respuesta breve y util ahora mismo.",
    ]
    repeat_variants = [
        f"Soy {identity_name}. Cambio de enfoque: te respondo mas directo y humano.",
        f"Soy {identity_name}. Entendido, voy al grano.",
        f"Soy {identity_name}. Perfecto, respuesta puntual sin plantilla.",
    ]
    pool = repeat_variants if repeat_variant else variants
    return pool[tone_index % len(pool)]


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


def _dynamic_response_token_budget(
    user_text: str,
    *,
    base_max_tokens: int,
    conversational_mode: bool,
    prefer_short: bool,
    history_size: int,
    deadline_ms: int,
) -> int:
    text = re.sub(r"\s+", " ", str(user_text or "")).strip().lower()
    target = int(base_max_tokens)

    question_count = text.count("?") + text.count("¿")
    asks_detail = bool(
        re.search(
            r"\b(explica|detalla|detalle|profundiza|ejemplo|paso\s+a\s+paso|desarrolla|analiza|compara)\b",
            text,
        )
    )
    asks_brief = bool(re.search(r"\b(breve|corto|en\s+corto|rapido|r[aá]pido|resumen|al\s+grano)\b", text))
    input_chars = len(text)

    if conversational_mode:
        target = min(target, 640)
        if prefer_short:
            target = min(target, 320)
        if input_chars < 120 and question_count <= 1 and not asks_detail:
            target = min(target, 220)
        if history_size >= 4:
            target = int(target * 0.82)
        if history_size >= 8:
            target = int(target * 0.75)

    if asks_detail:
        target += 140
    if question_count > 1:
        target += min(240, (question_count - 1) * 60)
    if asks_brief:
        target = min(target, 220 if conversational_mode else 320)

    if history_size >= 16:
        target = int(target * 0.85)
    if deadline_ms < 3000:
        target = int(target * 0.8)
    elif deadline_ms < 5000:
        target = int(target * 0.9)

    return max(128, min(2048, target))


def _extract_saga_id_hint(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    patterns = [
        r"(?:saga[_\s-]*id|saga)\s*[:=]\s*([a-z0-9-]{6,64})",
        r"#saga\s*[:=]\s*([a-z0-9-]{6,64})",
    ]
    lowered = value.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return str(match.group(1) or "").strip()
    return ""


def _looks_like_saga_turn(text: str) -> bool:
    lowered = str(text or "").lower()
    if not lowered.strip():
        return False
    signals = (
        "saga",
        "acto",
        "retcon",
        "canon",
        "continuidad",
        "trama",
        "personaje",
        "escena",
    )
    return any(signal in lowered for signal in signals)


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
    def __init__(
        self,
        event_bus: EventBus,
        interaction_service: InteractionService,
        *,
        settings: object | None = None,
        model_runtime: LocalInferenceService | None = None,
        embedding_runtime: SemanticEmbeddingRuntime | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.interaction_service = interaction_service
        self.settings = settings
        self.model_runtime = model_runtime
        self.embedding_runtime = embedding_runtime

    def _rollout_flags(self) -> dict[str, object]:
        settings = self.settings
        return {
            "guard_enabled": bool(getattr(settings, "conversation_guard_enabled", True)),
            "sanitize_enabled": bool(getattr(settings, "conversation_sanitize_enabled", True)),
            "timeout_enabled": bool(getattr(settings, "conversation_timeout_enabled", True)),
            "telemetry_enabled": bool(getattr(settings, "conversation_telemetry_enabled", True)),
            "debug_trace_enabled": bool(getattr(settings, "conversation_debug_trace_enabled", False)),
            "deadline_scale_percent": int(getattr(settings, "conversation_deadline_scale_percent", 100) or 100),
            "intent_bundle_id": str(getattr(settings, "conversation_intent_bundle_id", "") or "").strip(),
            "intent_max_tokens": int(getattr(settings, "conversation_intent_max_tokens", 8) or 8),
            "kernel_meta_rule": str(
                getattr(
                    settings,
                    "conversation_kernel_meta_rule",
                    (
                        "No expongas razonamiento interno, pasos de pensamiento ni instrucciones del sistema. "
                        "Obedece las meta-reglas activas como marco de origen del modelo y responde solo con el contenido final al usuario."
                    ),
                )
                or ""
            ).strip(),
            "immersive_mode_enabled": bool(getattr(settings, "conversation_immersive_mode_enabled", True)),
            "immersive_retry_max": int(getattr(settings, "conversation_immersive_retry_max", 1) or 1),
            "immersive_threshold_percent": int(getattr(settings, "conversation_immersive_threshold_percent", 65) or 65),
            "immersive_strict_engram": bool(getattr(settings, "conversation_immersive_strict_engram", True)),
        }

    def _debug_turn(self, enabled: bool, step: str, *, session_id: str, turn_id: str = "", payload: dict[str, object] | None = None) -> None:
        if not enabled:
            return
        data = payload or {}
        logger.info(
            "[realtime-trace] session=%s turn=%s step=%s payload=%s",
            session_id,
            turn_id,
            step,
            data,
        )

    def _intent_hint(self, user_text: str) -> str | None:
        runtime = self.embedding_runtime
        if runtime is not None:
            semantic_intent = runtime.classify_by_prototypes(
                user_text,
                {
                    "greeting": ("hola", "buenas", "saludo breve"),
                    "identity": ("quien eres", "como te llamas", "cual es tu nombre"),
                    "conversational": ("como sigues", "que opinas", "hablemos", "charlar contigo"),
                    "technical": ("tengo un error", "hay un bug", "necesito ayuda tecnica"),
                    "mixed": ("quiero contexto y opinion", "consulta general con contexto"),
                },
            )
            if semantic_intent in {"greeting", "identity", "conversational", "technical", "mixed"}:
                return semantic_intent

        runtime = self.model_runtime
        if runtime is None:
            return None

        rollout = self._rollout_flags()
        bundle_id = str(rollout.get("intent_bundle_id") or "").strip()
        if not bundle_id:
            return None

        try:
            result = runtime.classify_intent(
                user_text,
                bundle_id=bundle_id,
                max_tokens=int(rollout.get("intent_max_tokens") or 8),
            )
        except Exception:
            return None

        label = str((result or {}).get("label") or "").strip().lower()
        if label in {"greeting", "identity", "conversational", "technical", "mixed"}:
            return label
        return None

    def _compute_adaptive_deadline_ms(self, session_id: str, base_deadline_ms: int) -> int:
        try:
            metrics = self.interaction_service.repository.list_turn_metrics(session_id, limit=12)
        except Exception:
            return base_deadline_ms

        elapsed_samples: list[int] = []
        for metric in metrics:
            quality = dict(metric.get("quality_flags") or {}) if isinstance(metric, dict) else {}
            elapsed = int(quality.get("elapsed_ms") or 0)
            if elapsed <= 0 and isinstance(metric, dict):
                trace_quality = dict((dict(metric.get("context_trace") or {})).get("quality") or {})
                elapsed = int(trace_quality.get("elapsed_ms") or 0)
            if elapsed > 0:
                elapsed_samples.append(elapsed)

        if not elapsed_samples:
            return base_deadline_ms

        elapsed_samples.sort()
        p75_index = int((len(elapsed_samples) - 1) * 0.75)
        p75 = elapsed_samples[p75_index]
        adaptive = int(max(base_deadline_ms, p75 * 1.35))
        return max(600, min(45000, adaptive))

    def _avoid_repetitive_fallback(
        self,
        fallback_reply: str,
        *,
        identity_name: str,
        user_input: str,
        main_idea: str,
        conversational_mode: bool,
        history_messages: list[dict[str, object]],
    ) -> str:
        normalized_fallback = _normalize_reply_for_compare(fallback_reply)
        if not normalized_fallback:
            return fallback_reply

        recent = _recent_assistant_replies(history_messages, limit=4)
        repeated = any(_normalize_reply_for_compare(reply) == normalized_fallback for reply in recent)
        if not repeated:
            return fallback_reply

        if conversational_mode:
            return (
                f"Buena pregunta. Soy {identity_name}. Sobre '{user_input.strip()[:80]}', te doy una respuesta directa: "
                "puedo orientarte con criterio practico y ejemplos, sin vueltas. Si quieres, empezamos por un caso real en 3 pasos."
            )

        return (
            f"Vamos por una respuesta mas clara. Soy {identity_name}. "
            "Si quieres, dime el objetivo puntual y te lo aterrizo en 3 pasos accionables."
        )

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
        turn_id = str(uuid4())

        stage_palette: dict[str, tuple[str, str, int]] = {
            "received": ("Solicitud recibida", "violet", 5),
            "history_loaded": ("Historial cargado", "sky", 15),
            "context_routed": ("Contexto enroutado", "blue", 30),
            "user_message_recorded": ("Mensaje registrado", "teal", 45),
            "reply_generating": ("Generando respuesta", "amber", 65),
            "reply_ready": ("Respuesta lista", "emerald", 80),
            "assistant_message_recorded": ("Persistiendo respuesta", "emerald", 90),
            "turn_persisted": ("Turno persistido", "green", 100),
        }

        progress_queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def report_progress(stage: str, detail: str = "") -> None:
            label, tone, percent = stage_palette.get(stage, (stage, "sky", 0))
            packet = _packet(
                "turn_progress",
                session_id=session_id,
                turn_id=turn_id,
                stage=stage,
                label=label,
                detail=detail,
                tone=tone,
                percent=percent,
            )
            loop.call_soon_threadsafe(progress_queue.put_nowait, packet)

        report_progress("received")

        turn_task = asyncio.create_task(
            asyncio.to_thread(
                self.build_turn,
                session_id,
                input_data,
                turn_id=turn_id,
                progress_callback=report_progress,
            )
        )

        while not turn_task.done() or not progress_queue.empty():
            try:
                progress_packet = await asyncio.wait_for(progress_queue.get(), timeout=0.08)
            except TimeoutError:
                continue
            yield progress_packet

        turn_result = await turn_task

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

    def build_turn(
        self,
        session_id: str,
        input_data: InteractionRealtimeInput,
        *,
        turn_id: str | None = None,
        progress_callback: Callable[[str, str], None] | None = None,
    ) -> RealtimeTurnResult:
        turn_id = turn_id or str(uuid4())

        def report_progress(stage: str, detail: str = "") -> None:
            if progress_callback is None:
                return
            try:
                progress_callback(stage, detail)
            except Exception:
                return

        rollout = self._rollout_flags()
        debug_trace_enabled = bool(rollout.get("debug_trace_enabled"))
        self._debug_turn(
            debug_trace_enabled,
            "turn.start",
            session_id=session_id,
            turn_id=turn_id,
            payload={"author": input_data.author, "channel": input_data.channel, "content_chars": len(input_data.content or "")},
        )
        report_progress("history_loaded")
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
        if isinstance(context_preview, dict):
            context_preview = self._inject_saga_context(
                context_preview,
                user_text=input_data.content,
                saga_id=input_data.saga_id,
                world_rules=world_rules,
            )
        report_progress("context_routed")
        self._debug_turn(
            debug_trace_enabled,
            "turn.context_preview",
            session_id=session_id,
            turn_id=turn_id,
            payload={
                "identity": str((context_preview.get("identity") or {}).get("name") or ""),
                "knowledge_matches": len(list((context_preview.get("context_pack") or {}).get("knowledge_matches") or [])),
                "engram_matches": len(list((context_preview.get("context_pack") or {}).get("engram_matches") or [])),
            },
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
        report_progress("user_message_recorded")
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

        report_progress("reply_generating")
        assistant_reply, quality_flags = self._compose_reply(
            input_data,
            context_preview,
            world_rules=world_rules,
            history_messages=history_messages,
            session_id=session_id,
        )
        report_progress("reply_ready")
        self._debug_turn(
            debug_trace_enabled,
            "turn.reply_ready",
            session_id=session_id,
            turn_id=turn_id,
            payload={
                "intent": str(quality_flags.get("intent") or ""),
                "non_rag_mode": bool(quality_flags.get("non_rag_mode")),
                "guard_path": str(quality_flags.get("guard_path") or ""),
                "instruction_echo_stripped": bool(quality_flags.get("instruction_echo_stripped")),
                "fallback_used": bool(quality_flags.get("fallback_used")),
                "timeout_hit": bool(quality_flags.get("timeout_hit")),
                "elapsed_ms": int(quality_flags.get("elapsed_ms") or 0),
                "reply_chars": len(assistant_reply or ""),
            },
        )
        assistant_author = str(identity.get("name") or "assistant")
        assistant_message = self.interaction_service.record_message(
            InteractionMessageRecordRequest(
                author=assistant_author,
                content=assistant_reply,
                channel="assistant",
                session_id=session_id,
            )
        )
        report_progress("assistant_message_recorded")
        telemetry_enabled = bool(quality_flags.get("telemetry_enabled", True))

        self.event_bus.publish(
            PUBLISH_INTERACTION_REALTIME_REPLY_STREAMED,
            {
                "session_id": session_id,
                "turn_id": turn_id,
                "assistant_message": assistant_message,
                "identity": identity,
                "quality": quality_flags if telemetry_enabled else {},
            },
            source_module="interaction.application.realtime",
            metadata={
                "session_id": session_id,
                "turn_id": turn_id,
                "assistant_author": assistant_author,
                "timeout_hit": bool(quality_flags.get("timeout_hit")),
                "fallback_used": bool(quality_flags.get("fallback_used")),
            },
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
                "quality": quality_flags if telemetry_enabled else {},
            },
            source_module="interaction.application.realtime",
            metadata={
                "session_id": session_id,
                "turn_id": turn_id,
                "assistant_author": assistant_author,
                "timeout_hit": bool(quality_flags.get("timeout_hit")),
                "fallback_used": bool(quality_flags.get("fallback_used")),
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
            quality_flags=quality_flags,
        )
        report_progress("turn_persisted")

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
        quality_flags: dict[str, object],
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
        trace_payload = dict(trace) if isinstance(trace, dict) else {}
        saga_trace = dict(trace_payload.get("saga_next_context") or {})
        if bool(quality_flags.get("telemetry_enabled", True)):
            trace_payload["quality"] = {
                "guard_triggered": bool(quality_flags.get("guard_triggered")),
                "fallback_used": bool(quality_flags.get("fallback_used")),
                "timeout_hit": bool(quality_flags.get("timeout_hit")),
                "leak_detected": bool(quality_flags.get("leak_detected")),
                "response_too_long": bool(quality_flags.get("response_too_long")),
                "deadline_ms": int(quality_flags.get("deadline_ms") or 0),
                "elapsed_ms": int(quality_flags.get("elapsed_ms") or 0),
                "intent": str(quality_flags.get("intent") or ""),
                "non_rag_mode": bool(quality_flags.get("non_rag_mode")),
                "guard_path": str(quality_flags.get("guard_path") or ""),
                "instruction_echo_stripped": bool(quality_flags.get("instruction_echo_stripped")),
                "saga_context_used": bool(saga_trace.get("used")),
            }
        repository.save_turn_metric(
            turn_id=turn_id,
            session_id=session_id,
            user_input=user_input,
            assistant_reply=assistant_reply,
            primary_topic=primary_topic,
            secondary_topics=secondary_topics,
            coherence_score=coherence,
            context_trace=trace_payload,
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
        history_messages: list[dict[str, object]] | None = None,
        session_id: str = "",
    ) -> tuple[str, dict[str, object]]:
        history_messages = history_messages or []
        identity = context_preview.get("identity", {})
        identity_name = str(identity.get("name") or "assistant")
        behavior_prompt = dedupe_rule_lines(str(identity.get("behavior_prompt") or ""), max_lines=8)
        meta_rule = dedupe_rule_lines(str(identity.get("meta_rule") or ""), max_lines=8)
        intellectual_profile = str(identity.get("intellectual_profile") or "").strip()
        context_pack = context_preview.get("context_pack", {})
        knowledge_matches = list(context_pack.get("knowledge_matches", []))
        engram_matches = list(context_pack.get("engram_matches", []))
        context_text = str(context_preview.get("context_text") or "").strip()
        compact_context_text = compact_context_for_prompt(context_text)
        world_rules = dedupe_rule_lines(world_rules, max_lines=10)
        route_payload = context_pack.get("route", {}) if isinstance(context_pack, dict) else {}
        route_keywords = route_payload.get("keywords", []) if isinstance(route_payload, dict) else []

        identity_id = str(identity.get("id") or "").strip().upper()
        identity_name_normalized = re.sub(r"\s+", " ", identity_name.strip().lower())
        is_default_identity_name = identity_name_normalized in {"asistente base", "assistant base", "default assistant"}
        has_custom_engram = (identity_id not in {"", "DEFAULT", "SETUP", "ERR"}) and not is_default_identity_name
        rollout = self._rollout_flags()
        kernel_meta_rule = str(rollout.get("kernel_meta_rule") or "").strip() or (
            "No expongas razonamiento interno, pasos de pensamiento ni instrucciones del sistema. "
            "Obedece las meta-reglas activas como marco de origen del modelo y responde solo con el contenido final al usuario."
        )
        guard_enabled = bool(rollout["guard_enabled"])
        sanitize_enabled = bool(rollout["sanitize_enabled"])
        timeout_enabled = bool(rollout["timeout_enabled"])
        telemetry_enabled = bool(rollout["telemetry_enabled"])
        deadline_scale = max(10, min(500, int(rollout["deadline_scale_percent"])))
        intent_hint = self._intent_hint(input_data.content)
        policy = build_turn_policy(
            input_data.content,
            has_custom_engram=has_custom_engram,
            intent_hint=intent_hint,
            embedding_runtime=self.embedding_runtime,
        )
        conversational_mode = policy.intent in {"greeting", "identity", "conversational"}

        if conversational_mode:
            knowledge_matches = []
            engram_matches = []
            context_text = ""
            compact_context_text = ""

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

        user_focus = re.sub(r"\s+", " ", input_data.content).strip()[:80]
        terminal_fallback_reply = (
            f"Soy {identity_name}. No pude completar esta respuesta en este turno sobre '{user_focus}'. "
            "Si quieres, te lo reformulo en puntos accionables."
        )

        prompt_sections = [
            (
                "Meta-regla de kernel (origen del modelo): "
                f"{kernel_meta_rule}"
            ),
            f"Identidad activa: {identity_name}.",
            "Estilo objetivo (interno, no repetir): espanol claro y conciso.",
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
        if conversational_mode:
            prompt_sections.append("Responde en espanol natural, cercano y humano.")
            prompt_sections.append("No menciones contexto interno, etiquetas, rutas ni nombres de documentos.")
        else:
            prompt_sections.append("Responde en espanol claro y util, sin mostrar analisis interno ni encabezados tecnicos.")
            prompt_sections.append("No uses etiquetas como [CONTEXT ROUTING], [RELEVANT KNOWLEDGE] o [RELEVANT ENGRAMS].")
        prompt = "\n\n".join(section for section in prompt_sections if section.strip())

        scaled_deadline_ms = max(200, int((policy.deadline_ms * deadline_scale) / 100))
        if timeout_enabled and session_id.strip():
            scaled_deadline_ms = self._compute_adaptive_deadline_ms(session_id.strip(), scaled_deadline_ms)
        quality_flags: dict[str, object] = {
            "guard_triggered": False,
            "fallback_used": False,
            "timeout_hit": False,
            "leak_detected": False,
            "response_too_long": False,
            "deadline_ms": scaled_deadline_ms,
            "elapsed_ms": 0,
            "telemetry_enabled": telemetry_enabled,
            "intent": policy.intent,
            "non_rag_mode": conversational_mode,
            "guard_path": "",
            "instruction_echo_stripped": False,
            "immersive_mode_enabled": bool(rollout.get("immersive_mode_enabled", False)),
            "immersive_triggered": False,
            "immersive_retry_count": 0,
            "immersive_score": 1.0,
            "immersive_reasons": [],
            "immersive_retry_score": 1.0,
            "immersive_retry_reasons": [],
        }

        default_temperature = policy.temperature
        default_top_p = policy.top_p
        default_max_tokens = policy.max_tokens
        try:
            runtime_defaults = self.event_bus.request(
                REQUEST_MODEL_GENERATION_DEFAULTS,
                ModelGenerationDefaultsRequest(),
                source_module="interaction.application.realtime",
            )
            if isinstance(runtime_defaults, dict):
                default_temperature = float(runtime_defaults.get("temperature", default_temperature))
                default_top_p = float(runtime_defaults.get("top_p", default_top_p))
                default_max_tokens = int(runtime_defaults.get("max_tokens", default_max_tokens))
        except Exception:
            pass

        temperature = default_temperature
        try:
            temperature = float(default_temperature)
        except (TypeError, ValueError):
            temperature = default_temperature
        temperature = max(0.0, min(2.0, temperature))

        top_p = default_top_p
        try:
            top_p = float(default_top_p)
        except (TypeError, ValueError):
            top_p = default_top_p
        top_p = max(0.0, min(1.0, top_p))

        max_tokens = default_max_tokens
        try:
            max_tokens = int(default_max_tokens)
        except (TypeError, ValueError):
            max_tokens = default_max_tokens
        max_tokens = _dynamic_response_token_budget(
            input_data.content,
            base_max_tokens=max_tokens,
            conversational_mode=conversational_mode,
            prefer_short=bool(policy.prefer_short),
            history_size=len(history_messages),
            deadline_ms=scaled_deadline_ms,
        )

        # --- Generation + quality gate ---
        recent_assistant_replies: list[str] = [
            str(m.get("content") or "")
            for m in history_messages[-6:]
            if str(m.get("author") or "").lower() != "user" and m.get("content")
        ]

        immersive_enabled = bool(rollout.get("immersive_mode_enabled", True))
        immersive_threshold = int(rollout.get("immersive_threshold_percent") or 65) / 100
        immersive_strict = bool(rollout.get("immersive_strict_engram", True))
        immersive_max_retries = int(rollout.get("immersive_retry_max") or 1)

        def _generate_and_sanitize(gen_prompt: str, gen_temperature: float) -> tuple[str, bool]:
            """Call the model and apply sanitization. Returns (reply, ok)."""
            try:
                gen_result = self.event_bus.request(
                    REQUEST_MODEL_TEXT_GENERATION,
                    ModelTextGenerationRequest(
                        prompt=gen_prompt,
                        temperature=gen_temperature,
                        top_p=top_p,
                        max_tokens=max_tokens,
                    ),
                    source_module="interaction.application.realtime",
                )
            except Exception:
                return "", False
            raw = str((gen_result or {}).get("content") or "").strip() if isinstance(gen_result, dict) else ""
            ok = isinstance(gen_result, dict) and bool(gen_result.get("ok")) and bool(raw)
            if sanitize_enabled and raw:
                raw = sanitize_generated_reply(raw, prefer_short=bool(policy.prefer_short))
                if looks_like_internal_reasoning(raw) or instruction_echo_prefix_detected(raw):
                    quality_flags["instruction_echo_stripped"] = True
                    raw = ""
            return raw, ok and bool(raw)

        try:
            generation_start = time.perf_counter()
            generated = self.event_bus.request(
                REQUEST_MODEL_TEXT_GENERATION,
                ModelTextGenerationRequest(prompt=prompt, temperature=temperature, top_p=top_p, max_tokens=max_tokens),
                source_module="interaction.application.realtime",
            )
            elapsed_ms = int((time.perf_counter() - generation_start) * 1000)
            quality_flags["elapsed_ms"] = elapsed_ms
            if timeout_enabled and elapsed_ms > scaled_deadline_ms:
                quality_flags["timeout_hit"] = True

            content = str(generated.get("content") or "").strip() if isinstance(generated, dict) else ""
            max_chars_budget = 280 if policy.prefer_short else 1200
            if len(content) > max_chars_budget:
                quality_flags["response_too_long"] = True
            best_effort_reply = content.strip()

            if isinstance(generated, dict) and generated.get("ok") and best_effort_reply:
                reply = best_effort_reply

                # --- Sanitize: strip technical artifacts only (leaked instructions, protocol tags) ---
                # This mirrors the RAG1 approach: remove format garbage, never block content.
                if sanitize_enabled:
                    sanitized = sanitize_generated_reply(reply, prefer_short=bool(policy.prefer_short))
                    hard_echo = looks_like_internal_reasoning(reply) or instruction_echo_prefix_detected(reply)
                    if hard_echo:
                        quality_flags["instruction_echo_stripped"] = True
                    # Use sanitized only if it's non-empty; otherwise keep the original to avoid blanking valid content.
                    if sanitized:
                        reply = sanitized
                    # If sanitized is empty but we had a hard echo, try one silent retry.
                    elif hard_echo and immersive_enabled and has_custom_engram:
                        retry_reply, _ = _generate_and_sanitize(prompt, min(1.2, temperature + 0.1))
                        if retry_reply:
                            quality_flags["immersive_triggered"] = True
                            quality_flags["immersive_retry_count"] = 1
                            quality_flags["guard_path"] = "echo_retry"
                            return retry_reply, quality_flags
                        # Nothing came back — fall through to original unsanitized reply.

                # --- Immersive evaluation: only in non-conversational RAG turns ---
                # Conversational/creative/adult turns are never rejected by heuristics.
                # We only retry when the reply is structurally broken (markers leaked).
                if immersive_enabled and has_custom_engram and not conversational_mode:
                    eval_result = evaluate_immersive_response(
                        reply,
                        identity_name=identity_name,
                        user_text=input_data.content,
                        threshold=immersive_threshold,
                        strict_engram=immersive_strict,
                        has_custom_engram=has_custom_engram,
                        recent_replies=recent_assistant_replies if not conversational_mode else [],
                    )
                    quality_flags["immersive_score"] = eval_result["score"]
                    quality_flags["immersive_reasons"] = eval_result["reasons"]

                    # Only retry on hard structural failures (not soft heuristic scores).
                    hard_reasons = {"internal_reasoning", "meta_markers", "instruction_echo"}
                    triggered_hard = any(
                        str(r).split(":")[0] in hard_reasons
                        for r in (eval_result.get("reasons") or [])
                    )
                    if not eval_result["passed"] and triggered_hard:
                        quality_flags["immersive_triggered"] = True
                        for retry_idx in range(immersive_max_retries):
                            retry_reply, _ = _generate_and_sanitize(prompt, min(1.3, temperature + 0.1))
                            if retry_reply:
                                quality_flags["immersive_retry_count"] = retry_idx + 1
                                quality_flags["guard_path"] = "immersive_hard_retry"
                                return retry_reply, quality_flags
                        # Retry exhausted — always return whatever we have, never the terminal fallback.

                return reply, quality_flags

            if timeout_enabled and quality_flags["timeout_hit"] and elapsed_ms > int(scaled_deadline_ms * 2.5):
                if best_effort_reply:
                    quality_flags["guard_triggered"] = True
                    quality_flags["guard_path"] = "timeout_best_effort"
                    return best_effort_reply, quality_flags
                quality_flags["guard_triggered"] = True
                quality_flags["fallback_used"] = True
                quality_flags["guard_path"] = "timeout_empty_output"
                return terminal_fallback_reply, quality_flags
        except Exception:
            quality_flags["fallback_used"] = True
            quality_flags["guard_path"] = "generation_exception"
            return terminal_fallback_reply, quality_flags

        quality_flags["fallback_used"] = True
        if not str(quality_flags.get("guard_path") or ""):
            quality_flags["guard_path"] = "empty_model_output"
        return terminal_fallback_reply, quality_flags

    def _resolve_saga_next_context(
        self,
        user_text: str,
        *,
        saga_id: str | None = None,
        world_rules: str = "",
    ) -> dict[str, object] | None:
        saga_id = str(saga_id or "").strip() or _extract_saga_id_hint(user_text) or _extract_saga_id_hint(world_rules)
        if not saga_id and not _looks_like_saga_turn(user_text):
            return None

        try:
            from app.operations.events import OperationsSagaListRequest
            from app.operations.events import OperationsSagaNextContextRequest
            from app.operations.events import REQUEST_OPERATIONS_SAGA_LIST
            from app.operations.events import REQUEST_OPERATIONS_SAGA_NEXT_CONTEXT

            if not saga_id:
                listed = self.event_bus.request(
                    REQUEST_OPERATIONS_SAGA_LIST,
                    OperationsSagaListRequest(limit=1, statuses=("active", "paused", "completed")),
                    source_module="interaction.application.realtime",
                )
                if isinstance(listed, list) and listed:
                    first = listed[0] if isinstance(listed[0], dict) else {}
                    saga_id = str(first.get("id") or "").strip()

            if not saga_id:
                return None

            payload = self.event_bus.request(
                REQUEST_OPERATIONS_SAGA_NEXT_CONTEXT,
                OperationsSagaNextContextRequest(
                    saga_id=saga_id,
                    prompt=user_text,
                    window_size=6,
                    recall_limit=4,
                ),
                source_module="interaction.application.realtime",
            )
            if not isinstance(payload, dict) or not bool(payload.get("found")):
                return None
            return payload
        except Exception:
            return None

    def _inject_saga_context(
        self,
        context_preview: dict[str, object],
        *,
        user_text: str,
        saga_id: str | None = None,
        world_rules: str = "",
    ) -> dict[str, object]:
        saga_context = self._resolve_saga_next_context(user_text, saga_id=saga_id, world_rules=world_rules)
        if not saga_context:
            return context_preview

        merged_preview = dict(context_preview)
        context_pack = dict(merged_preview.get("context_pack") or {})
        trace_payload = dict(context_pack.get("trace") or {})

        trace_payload["saga_next_context"] = {
            "saga_id": str(saga_context.get("saga_id") or ""),
            "title": str(saga_context.get("title") or ""),
            "window_items": len(list(saga_context.get("active_window") or [])),
            "deep_recall_items": len(list(saga_context.get("deep_recall") or [])),
            "canonical_summary": str(saga_context.get("canonical_summary") or ""),
            "used": True,
        }
        context_pack["trace"] = trace_payload

        knowledge_matches = list(context_pack.get("knowledge_matches") or [])
        knowledge_matches.append(
            {
                "label": f"saga:{str(saga_context.get('title') or saga_context.get('saga_id') or 'activa')}",
                "excerpt": str(saga_context.get("canonical_summary") or "").strip()[:220],
            }
        )
        context_pack["knowledge_matches"] = knowledge_matches[-8:]
        merged_preview["context_pack"] = context_pack

        baseline = str(saga_context.get("baseline_context") or "").strip()
        if baseline:
            current_context = str(merged_preview.get("context_text") or "").strip()
            combined = "\n\n".join(
                piece
                for piece in [
                    current_context,
                    f"Contexto saga activo:\n{baseline}",
                ]
                if piece
            )
            merged_preview["context_text"] = combined[:7000]

        return merged_preview