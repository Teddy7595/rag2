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
    def __init__(self, response: dict[str, object]) -> None:
        self._response = response
        self.last_prompt = ""

    def request(self, spec, payload, source_module: str = "") -> dict[str, object]:
        if spec == REQUEST_MODEL_TEXT_GENERATION:
            self.last_prompt = str(payload.prompt)
            return dict(self._response)
        raise AssertionError(f"Unexpected request spec: {getattr(spec, 'name', spec)}")


@dataclass
class FakeSettings:
    conversation_guard_enabled: bool = True
    conversation_sanitize_enabled: bool = True
    conversation_timeout_enabled: bool = True
    conversation_telemetry_enabled: bool = True
    conversation_deadline_scale_percent: int = 100


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
    event_bus = FakeEventBus({"ok": True, "content": "contenido cualquiera"})
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
    assert "Buena pregunta" in reply
