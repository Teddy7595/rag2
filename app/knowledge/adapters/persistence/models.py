from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import DatabaseBase
from app.knowledge.domain import KnowledgeEntry


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeEntryRecord(DatabaseBase):
    __tablename__ = "knowledge_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    @classmethod
    def from_domain(cls, entry: KnowledgeEntry) -> "KnowledgeEntryRecord":
        return cls(
            id=str(entry.id),
            title=entry.title,
            content=entry.content,
            tags=list(entry.tags),
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )

    def to_domain(self) -> KnowledgeEntry:
        return KnowledgeEntry(
            id=str(self.id),
            title=self.title,
            content=self.content,
            tags=list(self.tags or []),
            created_at=self.created_at,
            updated_at=self.updated_at,
        )