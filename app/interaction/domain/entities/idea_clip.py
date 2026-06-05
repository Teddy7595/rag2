from __future__ import annotations

from dataclasses import dataclass, field

from app.core.base_entity import BaseEntity


@dataclass
class IdeaClip(BaseEntity):
    content: str
    label: str = ""
    source_message_id: str | None = None
    session_id: str | None = None
    tags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "content": self.content,
            "label": self.label,
            "source_message_id": self.source_message_id,
            "session_id": self.session_id,
            "tags": list(self.tags),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
