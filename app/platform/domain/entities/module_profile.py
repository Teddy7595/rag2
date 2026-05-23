from __future__ import annotations

from dataclasses import dataclass

from app.core.base_entity import BaseEntity


@dataclass
class ModuleProfile(BaseEntity):
    name: str
    summary: str
    stage: str = "alpha"

    def as_dict(self) -> dict[str, str | None]:
        return {
            "id": self.id,
            "name": self.name,
            "summary": self.summary,
            "stage": self.stage,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }