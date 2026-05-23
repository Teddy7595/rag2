from __future__ import annotations

from app.interaction.application.governance import (
    build_turn_policy,
    classify_intent,
    dedupe_rule_lines,
    sanitize_generated_reply,
    sanitize_history_content,
)


def test_build_turn_policy_prefers_short_for_greeting_and_identity() -> None:
    greeting_policy = build_turn_policy("hola", has_custom_engram=False)
    identity_policy = build_turn_policy("Sabes quien eres?", has_custom_engram=False)

    assert greeting_policy.intent == "greeting"
    assert greeting_policy.prefer_short is True
    assert greeting_policy.max_tokens <= 120
    assert greeting_policy.deadline_ms <= 1500

    assert identity_policy.intent == "identity"
    assert identity_policy.prefer_short is True
    assert identity_policy.max_tokens <= 160
    assert identity_policy.deadline_ms <= 1800


def test_build_turn_policy_allocates_more_budget_for_technical_queries() -> None:
    policy = build_turn_policy("Tengo un error websocket 404 en /ws/chat", has_custom_engram=True)

    assert policy.intent == "technical"
    assert policy.prefer_short is False
    assert policy.max_tokens >= 700
    assert policy.deadline_ms >= 3000


def test_sanitize_generated_reply_removes_internal_scaffolding() -> None:
    noisy = """
    Coincidencias relevantes:
    - smoke-doc [p1 #1] (score=1.50)
    Responde al usuario de forma directa, breve y util en espanol.
    user: hola
    assistant: respuesta
    """

    assert sanitize_generated_reply(noisy) == ""


def test_sanitize_generated_reply_removes_quoted_transcript_leaks() -> None:
    noisy = '"user: Hola, Sabes quien eres?\nAsistente Base: Si, soy Asistente Base\nCoincidencias relevantes:\n- smoke-doc"'
    assert sanitize_generated_reply(noisy) == ""


def test_sanitize_history_content_masks_internal_reasoning() -> None:
    masked = sanitize_history_content("1. **Analyze the Request:** user input")
    assert "omitida por seguridad" in masked


def test_dedupe_rule_lines_removes_repeated_lines() -> None:
    raw = "Regla A\nRegla A\n1. Regla A\nRegla B\n"
    deduped = dedupe_rule_lines(raw)

    lines = deduped.splitlines()
    assert lines == ["Regla A", "Regla B"]


def test_classify_intent_defaults_to_mixed_for_non_technical_content() -> None:
    assert classify_intent("Me gustan los domingos por la tarde") == "mixed"


def test_classify_intent_detects_conversational_queries() -> None:
    assert classify_intent("Que opinas del contenido para adultos?") == "conversational"


def test_build_turn_policy_for_conversational_queries() -> None:
    policy = build_turn_policy("Que piensas sobre relaciones y limites?", has_custom_engram=False)
    assert policy.intent == "conversational"
    assert policy.max_tokens >= 200
    assert policy.deadline_ms >= 2400
