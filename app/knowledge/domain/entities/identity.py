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
    dialogue_examples: list[str] = field(default_factory=list)
    backstory: str = ""

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
            "dialogue_examples": list(self.dialogue_examples),
            "backstory": self.backstory,
            "hint_handle": self.hint_handle(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }