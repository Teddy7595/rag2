from __future__ import annotations

from dataclasses import dataclass

from app.core.base_entity import BaseEntity


@dataclass
class ConversationMessage(BaseEntity):
    author: str
    content: str
    channel: str = "chat"
    session_id: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "author": self.author,
            "content": self.content,
            "channel": self.channel,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }