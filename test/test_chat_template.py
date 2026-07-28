from __future__ import annotations

from app.models.chat_template import render_chat_prompt

_CHATML_TEMPLATE = (
    "{%- if messages[0]['role'] == 'system' -%}"
    "{% set system_message = messages[0]['content'] %}{% set messages = messages[1:] %}"
    "{%- else -%}{% set system_message = '' %}{%- endif -%}"
    "{%- if system_message %}<|im_start|>system\n{{ system_message }}<|im_end|>\n{% endif -%}"
    "{%- for message in messages -%}"
    "<|im_start|>{{ message['role'] }}\n{{ message['content'] }}<|im_end|>\n"
    "{% endfor -%}"
    "{%- if add_generation_prompt -%}<|im_start|>assistant\n{%- endif -%}"
)

_MISTRAL_TEMPLATE = (
    "{%- if messages[0]['role'] == 'system' -%}"
    "{% set system_message = messages[0]['content'] %}{% set loop_messages = messages[1:] %}"
    "{%- else -%}{% set system_message = '' %}{% set loop_messages = messages %}{%- endif -%}"
    "{%- for message in loop_messages -%}"
    "{%- if message['role'] == 'user' -%}"
    "[INST] {{ message['content'] }} [/INST]"
    "{%- else -%}"
    "{{ message['content'] }}{{ eos_token }}"
    "{%- endif -%}"
    "{%- endfor -%}"
)

_BOS_LEAKING_TEMPLATE = "{{ bos_token }}" + _CHATML_TEMPLATE

_MALFORMED_TEMPLATE = "{% this is not valid jinja %}"


class FakeLlama:
    def __init__(self, metadata: dict[str, object], *, eos_id: int = 1, eos_text: bytes = b"<|im_end|>") -> None:
        self.metadata = metadata
        self._eos_id = eos_id
        self._eos_text = eos_text

    def token_eos(self) -> int:
        return self._eos_id

    def detokenize(self, tokens: list[int], special: bool = False) -> bytes:
        return self._eos_text


def test_render_chat_prompt_uses_native_tokens_for_chatml_template() -> None:
    llm = FakeLlama({"tokenizer.chat_template": _CHATML_TEMPLATE})
    result = render_chat_prompt(llm, "hello world", identity_name="Bot")

    assert result.rendered is True
    assert result.format_label == "chat_template.default"
    assert "<|im_start|>user" in result.prompt
    assert "hello world" in result.prompt
    assert "<|im_start|>assistant" in result.prompt
    assert "Bot:" not in result.prompt


def test_render_chat_prompt_uses_native_tokens_for_mistral_style_template() -> None:
    llm = FakeLlama({"tokenizer.chat_template": _MISTRAL_TEMPLATE}, eos_text=b"</s>")
    result = render_chat_prompt(llm, "hello world", identity_name="Bot")

    assert result.rendered is True
    assert "[INST]" in result.prompt
    assert "hello world" in result.prompt
    assert "[/INST]" in result.prompt
    assert "Bot:" not in result.prompt


def test_render_chat_prompt_single_user_message_renders_without_error() -> None:
    for template in (_CHATML_TEMPLATE, _MISTRAL_TEMPLATE):
        llm = FakeLlama({"tokenizer.chat_template": template})
        result = render_chat_prompt(llm, "solo un mensaje", identity_name="Bot")
        assert result.rendered is True
        assert result.prompt.strip()


def test_render_chat_prompt_falls_back_on_malformed_template() -> None:
    llm = FakeLlama({"tokenizer.chat_template": _MALFORMED_TEMPLATE})
    result = render_chat_prompt(llm, "contenido armado", identity_name="Bot")

    assert result.rendered is False
    assert result.format_label.startswith("legacy_fallback:exception")
    assert result.prompt == "contenido armado\n\nBot:"


def test_render_chat_prompt_falls_back_when_no_embedded_template() -> None:
    llm = FakeLlama({})
    result = render_chat_prompt(llm, "contenido armado", identity_name="Bot")

    assert result.rendered is False
    assert result.format_label == "legacy_fallback:no_embedded_template"
    assert result.prompt == "contenido armado\n\nBot:"


def test_render_chat_prompt_stop_list_is_additive() -> None:
    llm = FakeLlama({"tokenizer.chat_template": _CHATML_TEMPLATE}, eos_text=b"<|im_end|>")
    result = render_chat_prompt(llm, "hello world", identity_name="Bot")

    assert "<|im_end|>" in result.stop
    assert "<|im_start|>" in result.stop  # paired turn-open marker for ChatML
    for legacy_stop in ("<end_of_turn>", "<|eot_id|>", "</s>", "Human:", "User:", "usuario:", "Usuario:"):
        assert legacy_stop in result.stop


def test_render_chat_prompt_avoids_double_bos() -> None:
    llm = FakeLlama({"tokenizer.chat_template": _BOS_LEAKING_TEMPLATE})
    result = render_chat_prompt(llm, "hello world", identity_name="Bot")

    assert result.rendered is True
    assert "None" not in result.prompt
