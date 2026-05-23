from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import NAMESPACE_URL, uuid4, uuid5


@dataclass(kw_only=True)
class BaseEntity:
    id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        current_time = datetime.now(timezone.utc)
        if not self.id:
            self.id = self.generate_id()
        if self.created_at is None:
            self.created_at = current_time
        if self.updated_at is None:
            self.updated_at = self.created_at

    @staticmethod
    def generate_id() -> str:
        return str(uuid4())

    @staticmethod
    def build_stable_id(entity_name: str, raw_value: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"rag:{entity_name}:{raw_value}"))

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)