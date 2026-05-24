from __future__ import annotations

from dataclasses import dataclass
import re

from app.knowledge.application.embedding_runtime import SemanticEmbeddingRuntime
_INTENT_PROTOTYPES: dict[str, tuple[str, ...]] = {
    "greeting": (
        "hola",
        "buenas",
        "saludo breve",
        "solo quería saludar",
    ),
    "identity": (
        "quien eres",
        "como te llamas",
        "cual es tu nombre",
        "habla de tu identidad",
    ),
    "conversational": (
        "como sigues",
        "que opinas",
        "hablemos",
        "charlar contigo",
    ),
    "technical": (
        "tengo un error en la api",
        "hay un bug en el websocket",
        "necesito ayuda tecnica",
        "diagnostica el fallo",
    ),
    "mixed": (
        "quiero contexto y opinion",
        "mezcla de charla y soporte tecnico",
        "consulta general con contexto",
    ),
}


@dataclass(frozen=True)
class ConversationTurnPolicy:
    intent: str
    max_tokens: int
    temperature: float
    top_p: float
    deadline_ms: int
    prefer_short: bool = False


def build_turn_policy(
    user_text: str,
    *,
    has_custom_engram: bool,
    intent_hint: str | None = None,
    embedding_runtime: SemanticEmbeddingRuntime | None = None,
) -> ConversationTurnPolicy:
    intent = (intent_hint or classify_intent(user_text, embedding_runtime=embedding_runtime)).strip().lower()
    if intent not in {"greeting", "identity", "conversational", "technical", "mixed"}:
        intent = classify_intent(user_text, embedding_runtime=embedding_runtime)

    # Keep conservative budgets on default identity and allow larger budgets on custom engrams.
    if intent == "greeting":
        return ConversationTurnPolicy(
            intent=intent,
            max_tokens=140,
            temperature=0.45,
            top_p=0.95,
            deadline_ms=1700,
            prefer_short=True,
        )
    if intent == "identity":
        return ConversationTurnPolicy(
            intent=intent,
            max_tokens=220,
            temperature=0.4,
            top_p=0.95,
            deadline_ms=2200,
            prefer_short=True,
        )
    if intent == "conversational":
        return ConversationTurnPolicy(
            intent=intent,
            max_tokens=300 if has_custom_engram else 240,
            temperature=0.6 if has_custom_engram else 0.5,
            top_p=0.95,
            deadline_ms=3600,
            prefer_short=True,
        )
    if intent == "technical":
        return ConversationTurnPolicy(
            intent=intent,
            max_tokens=768 if has_custom_engram else 512,
            temperature=0.35 if has_custom_engram else 0.2,
            top_p=1.0 if has_custom_engram else 0.9,
            deadline_ms=3200,
            prefer_short=False,
        )
    return ConversationTurnPolicy(
        intent=intent,
        max_tokens=420 if has_custom_engram else 320,
        temperature=0.3 if has_custom_engram else 0.2,
        top_p=1.0 if has_custom_engram else 0.9,
        deadline_ms=2200,
        prefer_short=False,
    )


def classify_intent(text: str, *, embedding_runtime: SemanticEmbeddingRuntime | None = None) -> str:
    if embedding_runtime is not None:
        semantic_intent = embedding_runtime.classify_by_prototypes(text, _INTENT_PROTOTYPES)
        if semantic_intent in {"greeting", "identity", "conversational", "technical", "mixed"}:
            return semantic_intent

    if is_simple_greeting(text):
        return "greeting"
    if is_identity_question(text):
        return "identity"
    if is_conversational_query(text):
        return "conversational"

    lowered = text.lower()
    technical_markers = (
        "error",
        "trace",
        "stack",
        "api",
        "endpoint",
        "sql",
        "db",
        "websocket",
        "ws",
        "bug",
        "fix",
        "pytest",
        "modelo",
        "runtime",
    )
    if any(marker in lowered for marker in technical_markers):
        return "technical"
    return "mixed"


def is_conversational_query(text: str) -> bool:
    lowered = re.sub(r"\s+", " ", text.lower()).strip()
    lowered_compact = re.sub(r"[^a-z0-9áéíóúñ\s]", " ", lowered)
    lowered_compact = re.sub(r"\s+", " ", lowered_compact).strip()
    markers = (
        "que piensas",
        "que opinas",
        "como sigues",
        "como estas",
        "como va",
        "como asi",
        "que pasa",
        "que onda",
        "opinion",
        "opinión",
        "sobre ti",
        "cuentame sobre ti",
        "cuéntame sobre ti",
        "eres hostil",
        "eres agresivo",
        "eres amable",
        "eres serio",
        "eres robot",
        "eres un robot",
        "eres tonto",
        "eres retrasado",
        "eres mental",
        "contenido para adultos",
        "adultos",
        "como te sientes",
        "cómo te sientes",
        "charlar",
        "conversar",
        "hablas",
        "hablame",
        "háblame",
        "respondes",
        "tono",
        "normal",
        "hostil",
        "agresivo",
        "amable",
        "serio",
        "robot",
    )
    if any(marker in lowered for marker in markers):
        return True

    # Handle common typo variants in casual conversational prompts.
    conversational_patterns = (
        r"\bcomo\s+ha\s+est",
        r"\bcomo\s+est(?:a|as|an|do|toy)\b",
        r"\bque\s+tal\b",
        r"\best(?:a|as)\s+(?:agitad[oa]|cansad[oa]|nervios[oa]|ansios[oa]|trist[ea]|feliz|seri[oa]|hostil|amable|bien|mal)\b",
    )
    return any(re.search(pattern, lowered_compact) for pattern in conversational_patterns)


def dedupe_rule_lines(raw: str, *, max_lines: int = 10) -> str:
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


def compact_context_for_prompt(raw: str, *, max_lines: int = 8) -> str:
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


def is_simple_greeting(text: str) -> bool:
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
        greeting_openers = {"hola", "holi", "hello", "hi", "hey", "buenas", "buenos"}
        technical_tokens = {"error", "bug", "api", "sql", "db", "websocket", "endpoint"}
        if tokens[0] not in greeting_openers:
            return False
        if any(token in technical_tokens for token in tokens):
            return False
        if len(tokens) <= 9 and any(token in {"como", "que", "tal", "estas", "estdo", "sigues"} for token in tokens):
            return True
        return False
    non_greeting = [token for token in tokens if token not in greeting_tokens]
    return len(non_greeting) <= 1 and any(token in greeting_tokens for token in tokens)


def is_identity_question(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()
    patterns = (
        r"\bquien\s+eres\b",
        r"\bsabes\s+quien\s+eres\b",
        r"\bcual\s+es\s+tu\s+nombre\b",
        r"\bcomo\s+te\s+llamas\b",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def looks_like_internal_reasoning(text: str) -> bool:
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
        "coincidencias relevantes",
        "responde al usuario de forma directa",
        "solo muestra la respuesta final",
        "respuesta final y humana",
        "mensaje del usuario:",
        "identidad activa:",
        "ideas secundarias:",
        "perfil intelectual del engrama:",
        "instruccion de comportamiento del engrama:",
        "meta-regla del engrama:",
        "reglas del mundo activas para esta sesion:",
        "tono conversacional:",
        "resto del mensaje en ingles",
        "regla interna (no repetir)",
        "respuesta directa, breve y util en espanol",
        "**salida**",
    )
    if any(marker in lower for marker in markers):
        return True
    if re.search(r"\d+\.\s+\*\*", text):
        return True
    return False


def sanitize_history_content(text: str, *, max_chars: int = 500) -> str:
    content = text.strip()
    if looks_like_internal_reasoning(content):
        return "[respuesta interna omitida por seguridad]"
    if len(content) > max_chars:
        return content[:max_chars].rstrip() + "..."
    return content


def sanitize_generated_reply(text: str, *, prefer_short: bool = False, max_chars: int = 1200) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""

    # First strip leading prompt-echo directives so we can preserve any valid remainder.
    cleaned = _strip_instruction_echo_prefix(cleaned)
    if not cleaned:
        return ""

    if looks_like_internal_reasoning(cleaned):
        return ""

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    filtered: list[str] = []
    transcript_line_count = 0
    for line in lines:
        normalized = line.lstrip("\"'` ")
        lower = normalized.lower()
        if line.startswith("[") and line.endswith("]"):
            continue
        if lower.startswith(("intent:", "keywords:", "history:", "contexto recuperado:")):
            continue
        if lower.startswith(("regla interna", "respuesta directa, breve y util")):
            continue
        if "**salida**" in lower:
            continue
        if "score=" in lower:
            continue
        if lower.startswith(("user:", "assistant:", "asistente:", "usuario:")):
            transcript_line_count += 1
            continue
        if "coincidencias relevantes" in lower:
            continue
        filtered.append(normalized)

    if transcript_line_count >= 2:
        return ""

    result = "\n".join(filtered).strip()
    if not result:
        return ""

    if len(result) > max_chars:
        result = _truncate_complete_sentence(result, max_chars)

    if prefer_short and len(result) > 280:
        result = _truncate_complete_sentence(result, 280)

    if result.endswith("..."):
        trimmed = result[:-3].rstrip()
        if trimmed:
            result = f"{trimmed}."

    return result


def _truncate_complete_sentence(text: str, max_chars: int) -> str:
    content = str(text or "").strip()
    if len(content) <= max_chars:
        return content

    window = content[:max_chars].rstrip()
    if not window:
        return ""

    sentence_matches = list(re.finditer(r"[.!?](?:[\"')\]]+)?(?=\s|$)", window))
    if sentence_matches:
        candidate = window[: sentence_matches[-1].end()].rstrip()
        if len(candidate) >= max(80, int(max_chars * 0.45)):
            return candidate

    split_at = window.rfind(" ")
    candidate = window[:split_at].rstrip() if split_at > 0 else window
    candidate = candidate.rstrip(" ,:;-.")
    if not candidate:
        candidate = window.rstrip(" ,:;-")

    if not candidate:
        return ""
    if candidate[-1] not in ".!?":
        return f"{candidate}."
    return candidate


def _strip_instruction_echo_prefix(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip().strip('"\'` ')
    if not compact:
        return ""

    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", compact) if part.strip()]
    if not sentences:
        return compact

    if not instruction_echo_prefix_detected(sentences[0]):
        return compact

    while sentences and instruction_echo_prefix_detected(sentences[0]):
        sentences.pop(0)

    remainder = " ".join(sentences).strip()
    if remainder:
        return remainder
    return ""


def instruction_echo_prefix_detected(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip().strip('"\'` ')
    if not compact:
        return False
    first_sentence = re.split(r"(?<=[.!?])\s+", compact, maxsplit=1)[0].strip().strip('"\'` ')
    first_low = first_sentence.lower()
    instruction_echo_patterns = (
        r"\bsolo\s+(enfoca|muestra|coloca)\b.*\b(respuesta|usuario|bloque|texto)\b",
        r"\b(enfoca(?:te)?|enf[oó]cate|coloca|pon|escribe|redacta|responde|contesta)\b.*\b(respuesta|usuario|tono|bloque|texto|separaciones)\b",
        r"\bsolo\s+habla\s+de\s+forma\s+natural\b",
        r"\bno\s+uses?\s+etiquetas?\s+como\b",
        r"\bno\s+repitas?\s+el\s+enunciado\s+del\s+usuario\b",
        r"\bevitar\s+lenguaje\b.*\bformal\b",
        r"\bevitar?\s+metacomentarios\b",
        r"\bevitar?\s+.*\bexplicaciones?\b.*\bengrama",
        r"\breserv(?:a|ar)\b.*\betiquetas\s+internas\b",
        r"\betiquetas\s+internas\b.*\bprocesamiento\s+de\s+informaci[oó]n\b",
        r"\bahora\s*,?\s*escribe\b.*\b(historia|cuento|relato)\b",
        r"\brespuesta\s+del\s+engrama\b",
        r"\ben\s+un\s+solo\s+bloque\s+de\s+texto\b",
        r"\bno\s+separaciones\b",
    )
    return any(re.search(pattern, first_low) for pattern in instruction_echo_patterns)


def _token_overlap_ratio(a: str, b: str) -> float:
    """Fraction of meaningful tokens in *a* that also appear in *b*."""
    tokens_a = set(re.findall(r"[a-z0-9áéíóúñ]{3,}", a.lower()))
    tokens_b = set(re.findall(r"[a-z0-9áéíóúñ]{3,}", b.lower()))
    if not tokens_a:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a)


def detect_repetition(reply: str, recent_replies: list[str], *, threshold: float = 0.76) -> tuple[bool, float]:
    """Return (is_repetitive, max_overlap) comparing reply against recent assistant messages."""
    candidates = [r for r in recent_replies if r.strip()]
    if not candidates or not reply.strip():
        return False, 0.0
    max_overlap = max(_token_overlap_ratio(reply, prev) for prev in candidates)
    return max_overlap >= threshold, round(max_overlap, 3)


def evaluate_immersive_response(
    text: str,
    *,
    identity_name: str,
    user_text: str,
    threshold: float = 0.65,
    strict_engram: bool = True,
    has_custom_engram: bool = False,
    recent_replies: list[str] | None = None,
) -> dict[str, object]:
    candidate = re.sub(r"\s+", " ", str(text or "")).strip()
    score = 1.0
    reasons: list[str] = []
    hard_fail = False

    if not candidate:
        return {"score": 0.0, "passed": False, "reasons": ["empty"]}

    lowered = candidate.lower()

    if looks_like_internal_reasoning(candidate):
        score -= 0.85
        reasons.append("internal_reasoning")
        hard_fail = True

    if instruction_echo_prefix_detected(candidate):
        score -= 0.55
        reasons.append("instruction_echo")

    meta_markers = (
        "etiquetas internas",
        "procesamiento de informacion",
        "procesamiento de información",
        "contexto recuperado",
        "coincidencias relevantes",
        "respuesta del engrama",
        "analisis interno",
        "analyze the request",
        "drafting the response",
    )
    marker_hits = sum(1 for marker in meta_markers if marker in lowered)
    if marker_hits:
        score -= min(0.75, 0.25 * marker_hits)
        reasons.append("meta_markers")

    if len(candidate) < 20:
        score -= 0.12
        reasons.append("too_short")

    # Alignment check removed — heuristic-based persona/user alignment scoring
    # is too narrow for adult/creative content and causes valid responses to be rejected.

    # Repetition detection against recent assistant replies
    if recent_replies:
        is_repetitive, overlap = detect_repetition(candidate, recent_replies)
        if is_repetitive:
            score -= min(0.40, 0.20 + (overlap - 0.58) * 2.0)
            reasons.append(f"repetitive_content:{overlap:.2f}")
            if overlap >= 0.80:
                hard_fail = True

    score = max(0.0, min(1.0, round(score, 3)))
    passed = (score >= max(0.1, min(0.95, threshold))) and not hard_fail
    return {"score": score, "passed": passed, "reasons": reasons}
