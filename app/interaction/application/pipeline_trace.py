"""
Visual pipeline tracer for realtime conversation turns.

Activated by setting the env var:
    APP_PIPELINE_TRACE_ENABLED=true

Writes ANSI-colored output to stderr so it never mixes with app responses.
Each turn is self-contained: USER → INTENT → CONTEXT → HISTORY → PROMPT → REPLY.
"""
from __future__ import annotations

import os
import sys
from typing import Any

_ENABLED: bool = os.environ.get("APP_PIPELINE_TRACE_ENABLED", "").lower() in ("1", "true", "yes")

# ── ANSI palette ─────────────────────────────────────────────────────────────
_R  = "\033[0m"       # reset
_B  = "\033[1m"       # bold
_DIM = "\033[2m"      # dim

_CYAN   = "\033[36m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_MAGENTA= "\033[35m"
_RED    = "\033[31m"
_BLUE   = "\033[34m"
_WHITE  = "\033[97m"

_BOX_TOP    = "┌"
_BOX_MID    = "│"
_BOX_BOT    = "└"
_BOX_LINE   = "─"
_FILL       = 62

def _enabled() -> bool:
    return _ENABLED


def _w(text: str) -> None:
    """Write to stderr, flushing immediately."""
    sys.stderr.write(text + "\n")
    sys.stderr.flush()


def _box(label: str, color: str = _CYAN) -> str:
    pad = _FILL - len(label) - 3
    return f"{color}{_B}{_BOX_TOP}{_BOX_LINE} {label} {_BOX_LINE * max(0, pad)}{_R}"


def _row(text: str = "", color: str = _WHITE) -> str:
    return f"{_DIM}{_BOX_MID}{_R} {color}{text}{_R}"


def _end() -> str:
    return f"{_DIM}{_BOX_BOT}{_BOX_LINE * (_FILL - 1)}{_R}"


def _score_color(score: float) -> str:
    if score >= 0.75:
        return _GREEN
    if score >= 0.45:
        return _YELLOW
    return _RED


def _clip(text: str, max_chars: int = 100) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


# ── Public trace calls ────────────────────────────────────────────────────────

def trace_turn_start(
    *,
    turn_id: str,
    session_id: str,
    user_text: str,
    is_continuation: bool,
    rag_query: str,
) -> None:
    if not _enabled():
        return
    short_id = turn_id[-8:] if turn_id else "?"
    short_sid = session_id[-6:] if session_id else "?"
    _w("")
    _w(f"{_CYAN}{_B}{'═' * (_FILL + 1)}{_R}")
    _w(f"{_CYAN}{_B}  PIPELINE TRACE  turn={short_id}  session={short_sid}{_R}")
    _w(f"{_CYAN}{_B}{'═' * (_FILL + 1)}{_R}")

    _w(_box("USER", _BLUE))
    _w(_row(f'"{_clip(user_text, 120)}"', _WHITE))
    _w(_end())

    cont_label = f"{_GREEN}SÍ — RAG enriquecido{_R}" if is_continuation else f"{_DIM}NO{_R}"
    _w(_box("INTENT / QUERY", _MAGENTA))
    _w(_row(f"continuación  = {cont_label}"))
    if is_continuation:
        _w(_row(f"rag_query     = {_YELLOW}{_clip(rag_query, 110)}{_R}"))
    _w(_end())


def trace_context(
    *,
    identity_name: str,
    intent: str,
    max_tokens: int,
    temperature: float,
    deadline_ms: int,
    narrative_mode: bool,
    knowledge_matches: list[dict[str, Any]],
    history_loaded: int,
    history_injected: int,
) -> None:
    if not _enabled():
        return

    intent_color = _GREEN if intent == "narrative" else _YELLOW if intent == "mixed" else _CYAN
    _w(_box("CONTEXT", _CYAN))
    _w(_row(f"identity      = {_B}{identity_name}{_R}"))
    _w(_row(f"intent        = {intent_color}{_B}{intent}{_R}"))
    _w(_row(f"policy        = tokens={max_tokens}  temp={temperature:.2f}  deadline={deadline_ms // 1000}s"))
    _w(_row(f"mode          = {'NARRATIVA' if narrative_mode else 'normal'}"))

    match_count = len(knowledge_matches)
    _w(_row(f"rag_matches   = {match_count}"))
    for i, match in enumerate(knowledge_matches):
        score = float(match.get("score") or 0.0)
        label = str(match.get("label") or "?")
        excerpt = _clip(str(match.get("excerpt") or ""), 90)
        sc = _score_color(score)
        _w(_row(f"  [{i}] {sc}{score:.2f}{_R}  {_B}{label}{_R}  {_DIM}{excerpt}{_R}"))

    _w(_row(f"history       = loaded={history_loaded}  injected={history_injected}"))
    _w(_end())


def trace_prompt(*, blocks: list[str]) -> None:
    if not _enabled():
        return
    _w(_box("PROMPT BLOCKS", _YELLOW))
    for i, block in enumerate(blocks):
        first_line = _clip(block, 100)
        _w(_row(f"[{i + 1:02d}] {first_line}"))
    _w(_row(f"total = {len(blocks)} bloques  ·  {sum(len(b) for b in blocks)} chars"))
    _w(_end())


def trace_reply(
    *,
    reply_chars: int,
    elapsed_ms: int,
    guard_triggered: bool,
    fallback_used: bool,
    timeout_hit: bool,
) -> None:
    if not _enabled():
        return
    guard_s  = f"{_RED}ACTIVADO{_R}" if guard_triggered else f"{_GREEN}OK{_R}"
    fb_s     = f"{_RED}SÍ{_R}"      if fallback_used   else f"{_GREEN}NO{_R}"
    to_s     = f"{_RED}SÍ{_R}"      if timeout_hit     else f"{_GREEN}NO{_R}"
    _w(_box("REPLY", _GREEN))
    _w(_row(f"chars={reply_chars}  elapsed={elapsed_ms}ms"))
    _w(_row(f"guard={guard_s}  fallback={fb_s}  timeout={to_s}"))
    _w(_end())
    _w(f"{_DIM}{'─' * (_FILL + 1)}{_R}")
    _w("")
