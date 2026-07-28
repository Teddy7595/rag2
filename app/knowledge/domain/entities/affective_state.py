from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class AffectiveState:
    engram_id: str
    pleasure: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.0
    updated_at: datetime | None = None

    def clamped(self) -> "AffectiveState":
        return AffectiveState(
            engram_id=self.engram_id,
            pleasure=max(-1.0, min(1.0, self.pleasure)),
            arousal=max(-1.0, min(1.0, self.arousal)),
            dominance=max(-1.0, min(1.0, self.dominance)),
            updated_at=self.updated_at,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "engram_id": self.engram_id,
            "pleasure": self.pleasure,
            "arousal": self.arousal,
            "dominance": self.dominance,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
