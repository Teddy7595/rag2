"""Render the loaded model's own embedded chat template around an already-fully
assembled prompt string, instead of appending a naive "{identity_name}:" lead-in.

Why this exists: this codebase never calls create_chat_completion() for the main
chat path (only create_completion() with a hand-assembled flat prompt), so the
model never sees its own fine-tuned turn-boundary tokens (e.g. <|im_end|>,
<end_of_turn>). A plain "{identity_name}:" text lead-in reads like a screenplay
transcript, which invites chat-tuned models to hallucinate the next "speaker"
turn. Rendering the model's real Jinja2 chat_template (already embedded in most
GGUF files) around the same content gives the model its native stop signal
without touching how that content is assembled upstream.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_TURN_PAIR_STOP_BY_EOS: dict[str, str] = {
    "<|im_end|>": "<|im_start|>",
    "<end_of_turn>": "<start_of_turn>",
    "<|eot_id|>": "<|start_header_id|>",
}

_LEGACY_GENERIC_STOP: tuple[str, ...] = (
    "<end_of_turn>",
    "<|eot_id|>",
    "</assistant_response>",
    "<|im_end|>",
    "</s>",
    "Human:",
    "User:",
    "usuario:",
    "Usuario:",
)


@dataclass(frozen=True)
class RenderedPrompt:
    prompt: str
    stop: list[str] = field(default_factory=lambda: list(_LEGACY_GENERIC_STOP))
    rendered: bool = False
    format_label: str = "legacy_fallback"


def _legacy(assembled_content: str, identity_name: str, *, reason: str) -> RenderedPrompt:
    prompt = f"{assembled_content}\n\n{identity_name}:"
    return RenderedPrompt(
        prompt=prompt,
        stop=list(_LEGACY_GENERIC_STOP),
        rendered=False,
        format_label=f"legacy_fallback:{reason}",
    )


def render_chat_prompt(llm: object, assembled_content: str, *, identity_name: str) -> RenderedPrompt:
    """Wrap `assembled_content` (the already fully-assembled BLOCK1-5 text) in the
    loaded model's own chat_template. Falls back to the legacy plain-text lead-in
    on any failure — malformed template, missing tokens, unsupported model — so a
    template problem never blocks a turn."""
    try:
        metadata = getattr(llm, "metadata", None) or {}
        template = metadata.get("tokenizer.chat_template")
        if not template:
            return _legacy(assembled_content, identity_name, reason="no_embedded_template")

        from llama_cpp.llama_chat_format import Jinja2ChatFormatter

        eos_id = llm.token_eos()
        if eos_id is None or eos_id == -1:
            return _legacy(assembled_content, identity_name, reason="no_eos_token")
        eos_text = llm.detokenize([eos_id], special=True).decode("utf-8", errors="ignore")
        if not eos_text:
            return _legacy(assembled_content, identity_name, reason="empty_eos_text")

        formatter = Jinja2ChatFormatter(
            template=template,
            eos_token=eos_text,
            # create_completion() already auto-prepends the model's real BOS token
            # when tokenizing the final prompt string — passing the real bos_token
            # here too would render it a second time as literal text.
            bos_token="",
            add_generation_prompt=True,
            stop_token_ids=[eos_id],
        )
        # An explicit (even empty) system message matters: some templates (e.g.
        # Mistral/Ministral-family) inject their own default English system
        # prompt only when NO system-role message is present at all — passing
        # one, even blank, suppresses that and keeps our own identity/behavior
        # instructions (already baked into assembled_content) as the only voice.
        response = formatter(
            messages=[
                {"role": "system", "content": ""},
                {"role": "user", "content": assembled_content},
            ]
        )
        rendered_prompt = str(response.prompt or "")
        if not rendered_prompt.strip():
            return _legacy(assembled_content, identity_name, reason="empty_render")

        stop_list: list[str] = [eos_text]
        pair = _TURN_PAIR_STOP_BY_EOS.get(eos_text)
        if pair:
            stop_list.append(pair)
        for stop_token in _LEGACY_GENERIC_STOP:
            if stop_token not in stop_list:
                stop_list.append(stop_token)

        return RenderedPrompt(
            prompt=rendered_prompt,
            stop=stop_list,
            rendered=True,
            format_label="chat_template.default",
        )
    except Exception as exc:
        return _legacy(assembled_content, identity_name, reason=f"exception:{exc.__class__.__name__}")
