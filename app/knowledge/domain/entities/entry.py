from __future__ import annotations

from dataclasses import dataclass, field

from app.core.base_entity import BaseEntity


@dataclass
class KnowledgeEntry(BaseEntity):
    title: str
    content: str
    tags: list[str] = field(default_factory=list) #type: ignore

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "tags": list(self.tags),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }