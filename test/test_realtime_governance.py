from __future__ import annotations

from dataclasses import dataclass

from app.interaction.application.realtime import RealtimeChatService
from app.interaction.events import InteractionRealtimeInput
from app.models.events import REQUEST_MODEL_TEXT_GENERATION


class FakeRepository:
    def __init__(self, metrics: list[dict[str, object]] | None = None) -> None:
        self._metrics = metrics or []

    def list_turn_metrics(self, session_id: str, limit: int = 12) -> list[dict[str, object]]:
        return self._metrics[:limit]


@dataclass
class FakeInteractionService:
    repository: FakeRepository


class FakeEventBus:
    def __init__(self, response: dict[str, object] | list[dict[str, object]]) -> None:
        if isinstance(response, list):
            self._responses = [dict(item) for item in response]
        else:
            self._responses = [dict(response)]
        self.last_prompt = ""
        self.prompts: list[str] = []

    def request(self, spec, payload, source_module: str = "") -> dict[str, object]:
        if spec == REQUEST_MODEL_TEXT_GENERATION:
            self.last_prompt = str(payload.prompt)
            self.prompts.append(self.last_prompt)
            if len(self._responses) > 1:
                return self._responses.pop(0)
            return dict(self._responses[0])
        raise AssertionError(f"Unexpected request spec: {getattr(spec, 'name', spec)}")


class FakeIntentRuntime:
    def __init__(self, label: str) -> None:
        self.label = label
        self.calls: list[dict[str, object]] = []

    def classify_intent(self, prompt: str, *, bundle_id: str | None = None, max_tokens: int = 8) -> dict[str, object]:
        self.calls.append({"prompt": prompt, "bundle_id": bundle_id, "max_tokens": max_tokens})
        return {"ok": True, "label": self.label, "content": self.label}


class FakeSemanticEmbeddingRuntime:
    def __init__(self, label: str) -> None:
        self.label = label
        self.calls: list[str] = []

    def classify_by_prototypes(
        self,
        text: str,
        prototypes: dict[str, tuple[str, ...] | list[str]],
        *,
        threshold: float = 0.24,
        margin: float = 0.03,
    ) -> str | None:
        self.calls.append(text)
        return self.label


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


def test_compose_reply_uses_model_intent_hint_for_ambiguous_turn(monkeypatch) -> None:
    event_bus = FakeEventBus({"ok": True, "content": "Respuesta breve"})
    intent_runtime = FakeIntentRuntime("conversational")
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(conversation_deadline_scale_percent=10, conversation_intent_bundle_id="intent-small.gguf"),
        model_runtime=intent_runtime,
    )

    ticks = iter([40.0, 40.01])
    monkeypatch.setattr("app.interaction.application.realtime.time.perf_counter", lambda: next(ticks))

    _, quality = service._compose_reply(
        InteractionRealtimeInput(content="Seguimos?"),
        _base_context_preview(),
        session_id="session-intent-model",
    )

    assert intent_runtime.calls
    assert quality["fallback_used"] is False
    assert "Tono conversacional" in event_bus.last_prompt


def test_compose_reply_uses_embedding_intent_hint_for_ambiguous_turn(monkeypatch) -> None:
    event_bus = FakeEventBus({"ok": True, "content": "Respuesta breve"})
    embedding_runtime = FakeSemanticEmbeddingRuntime("conversational")
    service = RealtimeChatService(
        event_bus=event_bus,
        interaction_service=FakeInteractionService(repository=FakeRepository()),
        settings=FakeSettings(conversation_deadline_scale_percent=10),
        embedding_runtime=embedding_runtime,
    )

    ticks = iter([41.0, 41.01])
    monkeypatch.setattr("app.interaction.application.realtime.time.perf_counter", lambda: next(ticks))

    _, quality = service._compose_reply(
        InteractionRealtimeInput(content="Seguimos?"),
        _base_context_preview(),
        session_id="session-intent-embeddings",
    )

    assert embedding_runtime.calls
    assert quality["fallback_used"] is False
    assert "Tono conversacional" in event_bus.last_prompt


def test_compose_reply_chatty_query_uses_conversational_fallback_without_internal_labels(monkeypatch) -> None:
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
    assert "Soy Asistente Base" in reply
    assert "directo" in reply.lower() or "breve" in reply.lower() or "natural" in reply.lower()


def test_compose_reply_typoed_greeting_never_uses_smoke_doc_fallback(monkeypatch) -> None:
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
    assert "Soy Asistente Base" in reply or "Hola" in reply


def test_compose_reply_slang_greeting_returns_human_style_reply(monkeypatch) -> None:
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
    assert "soy asistente base" in reply.lower() or "hola" in reply.lower()


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
    assert "Instruccion de comportamiento del engrama" in event_bus.last_prompt


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
    assert reply.lower().startswith("si, es cierto")
    assert "solo enfoca" not in reply.lower()


def test_compose_reply_conversational_english_output_falls_back_to_spanish() -> None:
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

    assert quality["fallback_used"] is True
    assert quality["guard_path"] == "language_fallback_spanish"
    assert "soy mistress keynes" in reply.lower()


def test_compose_reply_adaptive_deadline_uses_recent_elapsed_samples(monkeypatch) -> None:
    event_bus = FakeEventBus({"ok": True, "content": "ok"})
    repository = FakeRepository(
        metrics=[
            {"quality_flags": {"elapsed_ms": 1000}},
            {"quality_flags": {"elapsed_ms": 2000}},
            {"quality_flags": {"elapsed_ms": 4000}},
            {"quality_flags": {"elapsed_ms": 8000}},
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
        InteractionRealtimeInput(content="Necesito ayuda con un endpoint"),
        _base_context_preview(),
        session_id="session-adaptive",
    )

    assert quality["timeout_hit"] is False
    assert quality["deadline_ms"] == 5400


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

    ticks = iter([20.0, 21.0])
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


def test_compose_reply_immersive_mode_retries_when_first_draft_is_meta() -> None:
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
    assert "etiquetas internas" not in reply.lower()
    assert "historia" in reply.lower()
