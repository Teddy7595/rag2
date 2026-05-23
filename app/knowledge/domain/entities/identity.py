from __future__ import annotations

from dataclasses import dataclass, field

from app.core.base_entity import BaseEntity


@dataclass
class Identity(BaseEntity):
    name: str
    avatar: str = ""
    color_hex: str = "#00ff41"
    intellectual_profile: str = "General"
    behavior_prompt: str = ""
    meta_rule: str = "Stay consistent with the selected identity."
    moral_threshold: int = 0
    interaction_mode: str = "Directo"
    dialogue_examples: list[str] = field(default_factory=list)
    backstory: str = ""
    temperatura_base: float = 0.8
    top_p_base: float = 1.0
    max_tokens_respuesta: int = 2048

    def resolved_temperature(
        self,
        default: float = 0.8,
        minimum: float = 0.0,
        maximum: float = 2.0,
    ) -> float:
        try:
            value = float(self.temperatura_base)
        except (TypeError, ValueError):
            value = default

        return max(minimum, min(maximum, value))

    def resolved_top_p(
        self,
        default: float = 1.0,
        minimum: float = 0.0,
        maximum: float = 1.0,
    ) -> float:
        try:
            value = float(self.top_p_base)
        except (TypeError, ValueError):
            value = default

        return max(minimum, min(maximum, value))

    def resolved_max_tokens(
        self,
        default: int = 2048,
        minimum: int = 64,
        maximum: int = 4096,
    ) -> int:
        try:
            value = int(self.max_tokens_respuesta)
        except (TypeError, ValueError):
            value = default

        return max(minimum, min(maximum, value))

    def generation_kwargs(
        self,
        *,
        temperature_default: float = 0.8,
        top_p_default: float = 1.0,
        max_tokens_default: int = 2048,
        seed: int | None = None,
    ) -> dict[str, float | int]:
        config: dict[str, float | int] = {
            "temperature": self.resolved_temperature(default=temperature_default),
            "top_p": self.resolved_top_p(default=top_p_default),
            "max_tokens": self.resolved_max_tokens(default=max_tokens_default),
        }
        if seed is not None:
            config["seed"] = int(seed)
        return config

    def hint_handle(self) -> str:
        return f"@{self.name}" if self.name else "@System"

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "avatar": self.avatar,
            "color_hex": self.color_hex,
            "intellectual_profile": self.intellectual_profile,
            "behavior_prompt": self.behavior_prompt,
            "meta_rule": self.meta_rule,
            "moral_threshold": self.moral_threshold,
            "interaction_mode": self.interaction_mode,
            "dialogue_examples": list(self.dialogue_examples),
            "backstory": self.backstory,
            "temperatura_base": self.temperatura_base,
            "top_p_base": self.top_p_base,
            "max_tokens_respuesta": self.max_tokens_respuesta,
            "resolved_temperature": self.resolved_temperature(),
            "resolved_top_p": self.resolved_top_p(),
            "resolved_max_tokens": self.resolved_max_tokens(),
            "hint_handle": self.hint_handle(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }