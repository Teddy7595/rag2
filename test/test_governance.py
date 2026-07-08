from __future__ import annotations

from app.interaction.application.governance import (
    build_turn_policy,
    classify_intent,
    dedupe_rule_lines,
    evaluate_immersive_response,
    instruction_echo_prefix_detected,
    sanitize_generated_reply,
    sanitize_history_content,
)


def test_build_turn_policy_prefers_short_for_greeting_and_identity() -> None:
    greeting_policy = build_turn_policy("hola", has_custom_engram=False)
    identity_policy = build_turn_policy("Sabes quien eres?", has_custom_engram=False)

    assert greeting_policy.intent == "greeting"
    assert greeting_policy.prefer_short is True
    assert greeting_policy.max_tokens <= 220
    assert greeting_policy.deadline_ms <= 8000

    assert identity_policy.intent == "identity"
    assert identity_policy.prefer_short is True
    assert identity_policy.max_tokens <= 220
    assert identity_policy.deadline_ms <= 8000


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


def test_sanitize_generated_reply_strips_meta_instruction_prefix() -> None:
    noisy = "Solo enfoca la respuesta al usuario. ¿Te refieres a mis historias? Puedo aclararlo en corto."
    cleaned = sanitize_generated_reply(noisy)
    assert cleaned.startswith("¿Te refieres a mis historias?")
    assert "solo enfoca la respuesta" not in cleaned.lower()


def test_instruction_echo_prefix_detected_matches_known_pattern() -> None:
    assert instruction_echo_prefix_detected("Coloca la respuesta en un solo bloque de texto sin separaciones. Si, es cierto.") is True
    assert instruction_echo_prefix_detected("Evitar lenguaje formal y academico.") is True
    assert instruction_echo_prefix_detected("Respuesta del engrama (Mistress Keynes): texto") is True
    assert instruction_echo_prefix_detected("Si, es cierto.") is False


def test_sanitize_generated_reply_strips_multiple_instruction_prefixes() -> None:
    noisy = "Evitar lenguaje formal y academico. Respuesta del engrama (Mistress Keynes): [resto del mensaje en ingles]. Si, te respondo directo."
    cleaned = sanitize_generated_reply(noisy)
    assert cleaned.startswith("Si, te respondo directo")


def test_sanitize_generated_reply_strips_metacommentary_directive_prefix() -> None:
    noisy = "Evita metacomentarios o explicaciones de la accion de los engramas. Hola, que gusto leerte de nuevo."
    cleaned = sanitize_generated_reply(noisy)
    assert cleaned.startswith("Hola, que gusto leerte")


def test_sanitize_generated_reply_strips_no_etiquetas_directive_prefix() -> None:
    noisy = "No uses etiquetas como [COMENTARIOS] o [META-INFO]. No repitas el enunciado del usuario. Hola, como sigues hoy?"
    cleaned = sanitize_generated_reply(noisy)
    assert cleaned.startswith("Hola, como sigues")


def test_sanitize_generated_reply_strips_internal_tags_reserve_prefix() -> None:
    noisy = "Reserve el uso de etiquetas internas al procesamiento de informacion. Ahora, escribe una historia completa."
    cleaned = sanitize_generated_reply(noisy)
    assert cleaned == ""


def test_sanitize_generated_reply_strips_internal_regla_and_salida_markers() -> None:
    noisy = (
        'Regla interna (no repetir): nunca mencionar al usuario en primera persona.\n'
        'Respuesta directa, breve y util en espanol. **Salida** ¡Que onda, compa!'
    )
    cleaned = sanitize_generated_reply(noisy)
    assert cleaned == ""


def test_sanitize_generated_reply_truncates_with_sentence_closure() -> None:
    noisy = (
        "Primera frase completa. Segunda frase completa. "
        "Tercera frase muy larga que termina quedand"
    )
    cleaned = sanitize_generated_reply(noisy, max_chars=58)
    assert cleaned.endswith(".")
    assert not cleaned.endswith("...")


def test_sanitize_generated_reply_normalizes_trailing_ellipsis() -> None:
    cleaned = sanitize_generated_reply("Te explico esto ahora...", max_chars=1200)
    assert cleaned == "Te explico esto ahora."


def test_sanitize_history_content_masks_internal_reasoning() -> None:
    masked = sanitize_history_content("1. **Analyze the Request:** user input")
    assert "omitida por seguridad" in masked


def test_dedupe_rule_lines_removes_repeated_lines() -> None:
    raw = "Regla A\nRegla A\n1. Regla A\nRegla B\n"
    deduped = dedupe_rule_lines(raw)

    lines = deduped.splitlines()
    assert lines == ["Regla A", "Regla B"]


def test_classify_intent_defaults_to_conversational_for_non_technical_content() -> None:
    assert classify_intent("Me gustan los domingos por la tarde") == "conversational"


def test_classify_intent_detects_conversational_queries() -> None:
    assert classify_intent("Que opinas del contenido para adultos?") == "conversational"


def test_classify_intent_detects_affective_state_questions() -> None:
    assert classify_intent("¿Estas agitada?") == "conversational"


def test_build_turn_policy_for_conversational_queries() -> None:
    policy = build_turn_policy("Que piensas sobre relaciones y limites?", has_custom_engram=False)
    assert policy.intent == "conversational"
    assert policy.max_tokens >= 700
    assert policy.deadline_ms >= 3000
    assert policy.prefer_short is False


def test_build_turn_policy_for_affective_state_question() -> None:
    policy = build_turn_policy("Estas agitada?", has_custom_engram=True)
    assert policy.intent == "conversational"
    assert policy.prefer_short is False


def test_evaluate_immersive_response_rejects_internal_meta_markers() -> None:
    payload = evaluate_immersive_response(
        "Reserve el uso de etiquetas internas al procesamiento de informacion.",
        identity_name="Mistress Keynes",
        user_text="Escribe una historia",
    )
    assert payload["passed"] is False
    assert float(payload["score"]) < 0.65


def test_evaluate_immersive_response_accepts_persona_aligned_reply() -> None:
    payload = evaluate_immersive_response(
        "Soy Mistress Keynes. Te cuento una historia breve, con tensión y cierre.",
        identity_name="Mistress Keynes",
        user_text="Cuéntame una historia",
        has_custom_engram=True,
    )
    assert payload["passed"] is True
