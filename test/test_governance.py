from __future__ import annotations

from app.interaction.application.governance import (
    build_turn_policy,
    dedupe_rule_lines,
    evaluate_immersive_response,
    instruction_echo_prefix_detected,
    sanitize_generated_reply,
    sanitize_history_content,
)


def test_build_turn_policy_is_identical_regardless_of_input_text() -> None:
    """No intent classification, no style/length routing — the engram's own
    behavior_prompt decides register and length, not a text heuristic."""
    greeting_policy = build_turn_policy("hola", has_custom_engram=False)
    technical_policy = build_turn_policy("Tengo un error websocket 404 en /ws/chat", has_custom_engram=True)
    long_request_policy = build_turn_policy("Cuentame una historia larga con muchos detalles", has_custom_engram=False)

    assert greeting_policy == technical_policy == long_request_policy
    assert greeting_policy.max_tokens == 3072
    assert greeting_policy.deadline_ms == 90000


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


def test_sanitize_generated_reply_drops_dangling_asterisk_when_cut_mid_action_in_sentence_path() -> None:
    prefix = "Hola, que bueno verte de nuevo por aqui otra vez despues de tanto tiempo. "
    action_open = "*Ella sonrie con calma mientras se acerca despacio hacia la puerta."
    suffix = " Se detiene por completo y espera en silencio durante largo rato antes de continuar hablando con mas calma todavia."
    text = prefix + action_open + suffix
    cut_index = len(prefix) + len(action_open)

    cleaned = sanitize_generated_reply(text, max_chars=cut_index)

    assert cleaned.count("*") % 2 == 0
    assert "Hola, que bueno verte" in cleaned


def test_sanitize_generated_reply_drops_dangling_asterisk_in_fallback_path() -> None:
    text = (
        "Hola amigo *camina despacio por el pasillo mientras piensa en muchas cosas "
        "distintas sin parar nunca de moverse de un lado a otro constantemente todo "
        "el tiempo sin descanso alguno y sigue asi por mucho mas tiempo todavia"
    )
    cleaned = sanitize_generated_reply(text, max_chars=60)

    assert cleaned.count("*") % 2 == 0


def test_sanitize_generated_reply_preserves_paired_asterisk_well_before_cut_point() -> None:
    prefix = "Hola, *sonrie* que bueno verte de nuevo por aqui. "
    padding = "Sigo hablando de otras cosas sin relacion durante un buen rato mas para rellenar el texto."
    text = prefix + padding

    cleaned = sanitize_generated_reply(text, max_chars=len(prefix) + 10)

    assert "*sonrie*" in cleaned


def test_sanitize_history_content_masks_internal_reasoning() -> None:
    masked = sanitize_history_content("1. **Analyze the Request:** user input")
    assert "omitida por seguridad" in masked


def test_dedupe_rule_lines_removes_repeated_lines() -> None:
    raw = "Regla A\nRegla A\n1. Regla A\nRegla B\n"
    deduped = dedupe_rule_lines(raw)

    lines = deduped.splitlines()
    assert lines == ["Regla A", "Regla B"]


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
