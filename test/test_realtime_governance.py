from __future__ import annotations

from dataclasses import dataclass

from app.interaction.application.realtime import RealtimeChatService
from app.interaction.domain import ConversationMessage
from app.interaction.events import InteractionRealtimeInput
from app.knowledge.events import REQUEST_KNOWLEDGE_AFFECTIVE_STATE_GET
from app.models.events import REQUEST_MODEL_GENERATION_DEFAULTS
from app.models.events import REQUEST_MODEL_TEXT_GENERATION


class FakeRepository:
    def __init__(
        self,
        metrics: list[dict[str, object]] | None = None,
        messages_by_id: dict[str, ConversationMessage] | None = None,
    ) -> None:
        self._metrics = metrics or []
        self._messages_by_id = messages_by_id or {}

    def list_turn_metrics(self, session_id: str, limit: int = 12) -> list[dict[str, object]]:
        return self._metrics[:limit]

    def get_by_id(self, message_id: str) -> ConversationMessage | None:
        return self._messages_by_id.get(message_id)


@dataclass
class FakeInteractionService:
    repository: FakeRepository


class FakeEventBus:
    def __init__(
        self,
        response: dict[str, object] | list[dict[str, object]],
        *,
        generation_defaults: dict[str, object] | None = None,
        affective_state: dict[str, object] | None = None,
    ) -> None:
        if isinstance(response, list):
            self._responses = [dict(item) for item in response]
        else:
            self._responses = [dict(response)]
        self._generation_defaults = dict(generation_defaults or {})
        self._affective_state = dict(affective_state) if affective_state is not None else None
        self.last_prompt = ""
        self.last_max_tokens = 0
        self.max_tokens_history: list[int] = []
        self.prompts: list[str] = []

    def request(self, spec, payload, source_module: str = "") -> dict[str, object]:
        if spec == REQUEST_MODEL_GENERATION_DEFAULTS:
            return dict(self._generation_defaults)
        if spec == REQUEST_KNOWLEDGE_AFFECTIVE_STATE_GET:
            if self._affective_state is None:
                raise AssertionError("Unexpected request spec: knowledge.affective_state.get.request")
            return dict(self._affective_state)
        if spec == REQUEST_MODEL_TEXT_GENERATION:
            self.last_prompt = str(payload.prompt)
            self.last_max_tokens = int(payload.max_tokens)
            self.max_tokens_history.append(self.last_max_tokens)
            self.prompts.append(self.last_prompt)
            if len(self._responses) > 1:
                return self._responses.pop(0)
            return dict(self._responses[0])
        raise AssertionError(f"Unexpected request spec: {getattr(spec, 'name', spec)}")


@dataclass
class FakeSettings:
    conversation_guard_enabled: bool = True
    conversation_sanitize_enabled: bool = True
    conversation_timeout_enabled: bool = True
    conversation_telemetry_enabled: bool = True
    conversation_deadline_scale_percent: int = 100
    conversation_intent_bundle_id: str | None = None
    conversation_intent_max_tokens: int = 8
    conversation_immersive_mode_enabled: bool = False
    conversation_immersive_retry_max: int = 1
    conversation_immersive_threshold_percent: int = 65
    conversation_immersive_strict_engram: bool = True


def _base_context_preview() -> dict[str, object]:
    return {
        "identity": {
            "id": "DEFAULT",
            "name": "Asistente Base",
            "behavior_prompt": "",
            "meta_rule": "",
            "intellectual_profile": "",
        },
        "context_pack": {
            "knowledge_matches": [
                {
                    "label": "smoke-doc",
                    "excerpt": "Contexto de prueba",
                }
            ],
            "engram_matches": [
                {"id": "engram-1", "name": "Atlas"},
            ],
            "route": {"keywords": ["contexto", "realtime"]},
        },
        "context_text": "Contexto recuperado de prueba",
    }


def _custom_engram_context_preview() -> dict[str, object]:
    payload = _base_context_preview()
    payload["identity"] = {
        "id": "ENGRAM-ATLAS",
        "name": "Mistress Keynes",
        "behavior_prompt": "Responde con elegancia, seguridad y tono estrategico.",
        "meta_rule": "- Mantener voz distintiva del engrama.",
        "intellectual_profile": "Operadora tactica",
    }
    return payload


def test_compose_reply_conversational_bypasses_rag_heavy_prompt() -> None:
    event_bus = FakeEventBus({"ok": True, "content": "Respuesta conversacional"})
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(),
    )

    reply, quality = service._compose_reply(
        InteractionRealtimeInput(content="Que opinas del contenido para adultos?"),
        _base_context_preview(),
        session_id="session-conv",
    )

    assert reply == "Respuesta conversacional"
    assert quality["fallback_used"] is False
    assert "Contexto recuperado:" not in event_bus.last_prompt
    assert "Coincidencias relevantes:" not in event_bus.last_prompt
    assert "smoke-doc" not in event_bus.last_prompt


def test_compose_reply_injects_quoted_message_when_reply_to_message_id_resolves() -> None:
    quoted = ConversationMessage(
        id="msg-quoted",
        author="user",
        content="Como puedo mejorar el rendimiento de mi API?",
    )
    event_bus = FakeEventBus({"ok": True, "content": "Respuesta conversacional"})
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(
            repository=FakeRepository(messages_by_id={"msg-quoted": quoted})
        ),
        settings=FakeSettings(),
    )

    reply, quality = service._compose_reply(
        InteractionRealtimeInput(content="Dame mas detalles", reply_to_message_id="msg-quoted"),
        _base_context_preview(),
        session_id="session-reply",
    )

    assert reply == "Respuesta conversacional"
    assert quality["fallback_used"] is False
    assert "<mensaje_citado" in event_bus.last_prompt
    assert "Como puedo mejorar el rendimiento de mi API?" in event_bus.last_prompt


def test_compose_reply_skips_quoted_message_block_when_id_unresolved() -> None:
    event_bus = FakeEventBus({"ok": True, "content": "Respuesta conversacional"})
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(),
    )

    reply, quality = service._compose_reply(
        InteractionRealtimeInput(content="Dame mas detalles", reply_to_message_id="msg-inexistente"),
        _base_context_preview(),
        session_id="session-reply",
    )

    assert reply == "Respuesta conversacional"
    assert quality["fallback_used"] is False
    assert "<mensaje_citado" not in event_bus.last_prompt


def test_compose_reply_uses_same_token_budget_for_greeting_and_conversational_turns() -> None:
    """No intent routing — greeting and casual turns get the same policy ceiling;
    the model decides how much of it to use via natural EOS."""
    event_bus = FakeEventBus(
        {"ok": True, "content": "Respuesta conversacional"},
        generation_defaults={"max_tokens": 4096, "temperature": 0.7, "top_p": 1.0},
    )
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(),
    )

    _, greeting_quality = service._compose_reply(
        InteractionRealtimeInput(content="Hola"),
        _base_context_preview(),
        session_id="session-dynamic-budget-greeting",
    )
    assert greeting_quality["fallback_used"] is False
    assert event_bus.last_max_tokens == 4096

    _, conversational_quality = service._compose_reply(
        InteractionRealtimeInput(content="Como estas?"),
        _base_context_preview(),
        session_id="session-dynamic-budget-conv",
    )
    assert conversational_quality["fallback_used"] is False
    assert event_bus.last_max_tokens == 4096


def test_compose_reply_dynamic_budget_expands_on_detailed_technical_prompt() -> None:
    event_bus = FakeEventBus(
        {"ok": True, "content": "Respuesta tecnica detallada"},
        generation_defaults={"max_tokens": 4096, "temperature": 0.4, "top_p": 1.0},
    )
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(),
    )

    _, quality = service._compose_reply(
        InteractionRealtimeInput(content="Explica paso a paso el error websocket 404 y compara dos soluciones con ejemplos."),
        _custom_engram_context_preview(),
        session_id="session-dynamic-budget-tech",
    )

    assert quality["fallback_used"] is False
    assert event_bus.last_max_tokens >= 640


def test_compose_reply_maintains_full_budget_across_conversational_chain() -> None:
    event_bus = FakeEventBus(
        [
            {"ok": True, "content": "Han pasado semanas desde la ultima conversacion. Como sigues?"},
            {"ok": True, "content": "No uses etiquetas como [COMENTARIOS]. *Sonrio con calma* Estoy bien, gracias por preguntar."},
            {"ok": True, "content": "Solo habla de forma natural. *Cruzo los brazos* He estado ocupada, pero sigo aqui."},
        ],
        generation_defaults={"max_tokens": 4096, "temperature": 0.75, "top_p": 1.0},
    )
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(),
    )

    history_messages: list[dict[str, object]] = []

    reply_1, quality_1 = service._compose_reply(
        InteractionRealtimeInput(content="Como sigues hoy?"),
        _custom_engram_context_preview(),
        history_messages=history_messages,
        session_id="session-chain-1",
    )
    history_messages.extend(
        [
            {"author": "user", "channel": "chat", "content": "Como sigues hoy?"},
            {"author": "Mistress Keynes", "channel": "assistant", "content": reply_1},
        ]
    )

    reply_2, quality_2 = service._compose_reply(
        InteractionRealtimeInput(content="Como te sientes hoy?"),
        _custom_engram_context_preview(),
        history_messages=history_messages,
        session_id="session-chain-2",
    )
    history_messages.extend(
        [
            {"author": "user", "channel": "chat", "content": "Como te sientes hoy?"},
            {"author": "Mistress Keynes", "channel": "assistant", "content": reply_2},
        ]
    )

    reply_3, quality_3 = service._compose_reply(
        InteractionRealtimeInput(content="Hablemos normal, como te sientes ahora?"),
        _custom_engram_context_preview(),
        history_messages=history_messages,
        session_id="session-chain-3",
    )

    assert quality_1["fallback_used"] is False
    assert quality_2["fallback_used"] is False
    assert quality_3["fallback_used"] is False
    assert event_bus.max_tokens_history[0] == 4096
    assert event_bus.max_tokens_history[1] == 4096
    assert event_bus.max_tokens_history[2] == 4096
    assert "no uses etiquetas" not in reply_2.lower()
    assert "estoy bien, gracias por preguntar" in reply_2.lower()
    assert "solo habla de forma natural" not in reply_3.lower()
    assert "he estado ocupada" in reply_3.lower()


def test_compose_reply_chatty_query_with_empty_model_output_returns_operational_fallback(monkeypatch) -> None:
    event_bus = FakeEventBus({"ok": True, "content": ""})
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(conversation_deadline_scale_percent=10),
    )

    ticks = iter([30.0, 30.02])
    monkeypatch.setattr("app.interaction.application.realtime.time.perf_counter", lambda: next(ticks))

    reply, quality = service._compose_reply(
        InteractionRealtimeInput(content="Como sigues?"),
        _base_context_preview(),
        session_id="session-chatty",
    )

    assert quality["fallback_used"] is True
    assert "smoke-doc" not in reply
    assert "contexto" not in reply.lower()
    assert "soy asistente base" in reply.lower()
    assert "puntos accionables" in reply.lower()


def test_compose_reply_typoed_greeting_with_empty_model_output_uses_operational_fallback(monkeypatch) -> None:
    event_bus = FakeEventBus({"ok": True, "content": ""})
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(conversation_deadline_scale_percent=10),
    )

    ticks = iter([32.0, 32.03])
    monkeypatch.setattr("app.interaction.application.realtime.time.perf_counter", lambda: next(ticks))

    reply, quality = service._compose_reply(
        InteractionRealtimeInput(content="Hola srta Keynes ¿Como ha estdo?"),
        _base_context_preview(),
        session_id="session-typo-greeting",
    )

    assert quality["fallback_used"] in {False, True}
    assert "smoke-doc" not in reply
    assert "punto principal" not in reply.lower()
    assert "contexto" not in reply.lower()
    assert "soy asistente base" in reply.lower()
    assert "puntos accionables" in reply.lower()


def test_compose_reply_slang_greeting_with_empty_model_output_uses_operational_fallback(monkeypatch) -> None:
    event_bus = FakeEventBus({"ok": True, "content": ""})
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(conversation_deadline_scale_percent=10),
    )

    ticks = iter([33.0, 33.03])
    monkeypatch.setattr("app.interaction.application.realtime.time.perf_counter", lambda: next(ticks))

    reply, quality = service._compose_reply(
        InteractionRealtimeInput(content="Que lo que, bro? Todo bien o que?"),
        _base_context_preview(),
        session_id="session-slang-greeting",
    )

    assert quality["fallback_used"] is True
    assert "contexto" not in reply.lower()
    assert "smoke-doc" not in reply.lower()
    assert "soy asistente base" in reply.lower()
    assert "puntos accionables" in reply.lower()


def test_compose_reply_story_request_never_leaks_internal_labels(monkeypatch) -> None:
    event_bus = FakeEventBus({"ok": True, "content": ""})
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(conversation_deadline_scale_percent=10),
    )

    ticks = iter([34.0, 34.02])
    monkeypatch.setattr("app.interaction.application.realtime.time.perf_counter", lambda: next(ticks))

    reply, quality = service._compose_reply(
        InteractionRealtimeInput(content="Hazme una historia corta de ciencia ficcion en tono calle."),
        _base_context_preview(),
        session_id="session-story-request",
    )

    assert quality["fallback_used"] is True
    assert "contexto recuperado" not in reply.lower()
    assert "coincidencias relevantes" not in reply.lower()
    assert "smoke-doc" not in reply.lower()
    assert len(reply.strip()) > 20


def test_custom_engram_greeting_uses_model_generation_not_default_guard() -> None:
    event_bus = FakeEventBus({"ok": True, "content": "Buenas, soy Mistress Keynes. Estoy lista."})
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(conversation_deadline_scale_percent=100),
    )

    reply, quality = service._compose_reply(
        InteractionRealtimeInput(content="Hola Keynes, como sigues?"),
        _custom_engram_context_preview(),
        session_id="session-custom-engram-greeting",
    )

    assert reply == "Buenas, soy Mistress Keynes. Estoy lista."
    assert quality["fallback_used"] is False
    assert quality["guard_path"] == ""
    assert "Modo de conducta" in event_bus.last_prompt


def test_compose_reply_injects_pad_tone_clause_for_custom_engram_with_affective_state() -> None:
    event_bus = FakeEventBus(
        {"ok": True, "content": "Respuesta"},
        affective_state={"engram_id": "ENGRAM-ATLAS", "pleasure": 0.6, "arousal": 0.5, "dominance": 0.4},
    )
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(),
    )

    service._compose_reply(
        InteractionRealtimeInput(content="Como sigues hoy?"),
        _custom_engram_context_preview(),
        session_id="session-pad-tone",
    )

    assert "Ahora mismo, respondes" in event_bus.last_prompt
    assert event_bus.last_prompt.count("Ahora mismo,") == 1


def test_compose_reply_omits_pad_tone_clause_when_affective_state_is_neutral() -> None:
    event_bus = FakeEventBus(
        {"ok": True, "content": "Respuesta"},
        affective_state={"engram_id": "ENGRAM-ATLAS", "pleasure": 0.0, "arousal": 0.0, "dominance": 0.0},
    )
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(),
    )

    service._compose_reply(
        InteractionRealtimeInput(content="Como sigues hoy?"),
        _custom_engram_context_preview(),
        session_id="session-pad-neutral",
    )

    assert "Ahora mismo," not in event_bus.last_prompt


def test_compose_reply_omits_pad_tone_clause_on_saga_channel() -> None:
    event_bus = FakeEventBus(
        {"ok": True, "content": "Respuesta"},
        affective_state={"engram_id": "ENGRAM-ATLAS", "pleasure": 0.6, "arousal": 0.5, "dominance": 0.4},
    )
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(),
    )

    service._compose_reply(
        InteractionRealtimeInput(content="Continua la escena", channel="saga", saga_id="saga-1"),
        _custom_engram_context_preview(),
        session_id="session-pad-saga",
    )

    assert "Ahora mismo," not in event_bus.last_prompt


def test_compose_reply_omits_pad_tone_clause_without_custom_engram() -> None:
    event_bus = FakeEventBus(
        {"ok": True, "content": "Respuesta"},
        affective_state={"engram_id": "DEFAULT", "pleasure": 0.8, "arousal": 0.8, "dominance": 0.8},
    )
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(),
    )

    service._compose_reply(
        InteractionRealtimeInput(content="Como estas?"),
        _base_context_preview(),
        session_id="session-pad-no-engram",
    )

    assert "Ahora mismo," not in event_bus.last_prompt


def test_compose_reply_includes_voice_register_instruction_on_generic_turn() -> None:
    event_bus = FakeEventBus({"ok": True, "content": "Respuesta"})
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(),
    )

    service._compose_reply(
        InteractionRealtimeInput(content="Como estas hoy?"),
        _custom_engram_context_preview(),
        session_id="session-voice-register-generic",
    )

    assert "acotaciones de acción entre asteriscos" in event_bus.last_prompt


def test_compose_reply_omits_voice_register_instruction_on_saga_channel() -> None:
    event_bus = FakeEventBus({"ok": True, "content": "Respuesta"})
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(),
    )

    service._compose_reply(
        InteractionRealtimeInput(content="Continua la escena", channel="saga", saga_id="saga-1"),
        _custom_engram_context_preview(),
        session_id="session-voice-register-saga",
    )

    assert "acotaciones de acción entre asteriscos" not in event_bus.last_prompt


def test_compose_reply_omits_voice_register_instruction_on_continuation_turn() -> None:
    event_bus = FakeEventBus(
        [
            {"ok": True, "content": "*Se acerca despacio* Sigo aqui esperando tu respuesta con calma."},
            {"ok": True, "content": "Continua la narracion sin repetir lo anterior."},
        ]
    )
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(),
    )
    history_messages: list[dict[str, object]] = [
        {"author": "user", "channel": "chat", "content": "Hola"},
        {"author": "Mistress Keynes", "channel": "assistant", "content": "*Se acerca despacio* Sigo aqui esperando tu respuesta con calma."},
    ]

    service._compose_reply(
        InteractionRealtimeInput(content="Sigue con la historia"),
        _custom_engram_context_preview(),
        history_messages=history_messages,
        session_id="session-voice-register-continuation",
    )

    assert "acotaciones de acción entre asteriscos" not in event_bus.last_prompt


def test_compose_reply_sets_instruction_echo_flag_when_prefix_is_stripped() -> None:
    event_bus = FakeEventBus(
        {
            "ok": True,
            "content": "Solo enfoca la respuesta al usuario. Si, es cierto y te respondo directo.",
        }
    )
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(conversation_deadline_scale_percent=100),
    )

    reply, quality = service._compose_reply(
        InteractionRealtimeInput(content="Responde claro"),
        _custom_engram_context_preview(),
        session_id="session-instruction-echo",
    )

    assert quality["instruction_echo_stripped"] is True
    assert "solo enfoca la respuesta" not in reply.lower()
    assert "si, es cierto y te respondo directo" in reply.lower()


def test_compose_reply_conversational_english_output_prefers_model_reply() -> None:
    event_bus = FakeEventBus(
        {
            "ok": True,
            "content": "I can answer your question directly and clearly if you want to continue this conversation.",
        }
    )
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(conversation_deadline_scale_percent=100),
    )

    reply, quality = service._compose_reply(
        InteractionRealtimeInput(content="Como sigues?"),
        _custom_engram_context_preview(),
        session_id="session-english-fallback",
    )

    assert quality["fallback_used"] is False
    assert quality["guard_path"] == ""
    assert "i can answer your question directly" in reply.lower()


def test_compose_reply_adaptive_deadline_uses_recent_elapsed_samples(monkeypatch) -> None:
    # The unified policy now sets a single 90000ms base deadline for every turn,
    # which always exceeds the adaptive p75 formula's 45000ms ceiling — so the
    # ceiling is what surfaces regardless of the elapsed-time history samples.
    event_bus = FakeEventBus({"ok": True, "content": "ok"})
    repository = FakeRepository(
        metrics=[
            {"quality_flags": {"elapsed_ms": 5000}},
            {"quality_flags": {"elapsed_ms": 10000}},
            {"quality_flags": {"elapsed_ms": 20000}},
            {"quality_flags": {"elapsed_ms": 30000}},
        ]
    )
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=repository),
        settings=FakeSettings(conversation_deadline_scale_percent=100),
    )

    ticks = iter([10.0, 10.01])
    monkeypatch.setattr("app.interaction.application.realtime.time.perf_counter", lambda: next(ticks))

    _, quality = service._compose_reply(
        InteractionRealtimeInput(content="Hola"),
        _base_context_preview(),
        session_id="session-adaptive",
    )

    assert quality["timeout_hit"] is False
    assert quality["deadline_ms"] == 45000


def test_compose_reply_timeout_repetition_switches_to_diverse_fallback(monkeypatch) -> None:
    event_bus = FakeEventBus({"ok": True, "content": ""})
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(conversation_deadline_scale_percent=10),
    )

    user_text = "Que opinas del contenido para adultos?"
    repeated_fallback = (
        "Soy Asistente Base. Te leo: 'Que opinas del contenido para adultos?'. "
        "Dime que necesitas y te respondo directo y en corto."
    )
    history_messages = [
        {"author": "Asistente Base", "channel": "assistant", "content": repeated_fallback},
    ]

    # base deadline is now 90000ms (non-greeting/identity), scaled to 9000ms at
    # 10%; the diverse-fallback path additionally requires elapsed > 2.5x that
    # (22500ms), so the mocked elapsed needs to clear both thresholds.
    ticks = iter([20.0, 45.0])
    monkeypatch.setattr("app.interaction.application.realtime.time.perf_counter", lambda: next(ticks))

    reply, quality = service._compose_reply(
        InteractionRealtimeInput(content=user_text),
        _base_context_preview(),
        history_messages=history_messages,
        session_id="session-repeat",
    )

    assert quality["timeout_hit"] is True
    assert quality["fallback_used"] is True
    assert reply != repeated_fallback
    assert "smoke-doc" not in reply
    assert "contexto" not in reply.lower()


def test_compose_reply_immersive_mode_retries_on_leaked_scaffolding_and_uses_clean_reply() -> None:
    event_bus = FakeEventBus(
        [
            {
                "ok": True,
                "content": "Reserve el uso de etiquetas internas al procesamiento de informacion. Ahora, escribe una historia completa.",
            },
            {
                "ok": True,
                "content": "Soy Mistress Keynes. Te cuento una historia breve: una ciudad sin luna, un pacto roto y un final que respira esperanza.",
            },
        ]
    )
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(
            conversation_immersive_mode_enabled=True,
            conversation_immersive_retry_max=1,
            conversation_immersive_threshold_percent=65,
            conversation_immersive_strict_engram=True,
        ),
    )

    reply, quality = service._compose_reply(
        InteractionRealtimeInput(content="Escribe una historia completa, con intro, body y conclusion."),
        _custom_engram_context_preview(),
        session_id="session-immersive-retry",
    )

    assert quality["immersive_triggered"] is True
    assert quality["immersive_retry_count"] == 1
    assert quality["fallback_used"] is False
    assert "reserve el uso de etiquetas internas" not in reply.lower()
    assert "una ciudad sin luna" in reply.lower()
