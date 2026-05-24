from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import DatabaseBase
from app.knowledge.domain import Identity, KnowledgeEntry


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeEntryRecord(DatabaseBase):
    __tablename__ = "knowledge_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="manual", index=True)
    source_uri: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    document_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    document_title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    @classmethod
    def from_domain(cls, entry: KnowledgeEntry) -> "KnowledgeEntryRecord":
        return cls(
            id=str(entry.id),
            title=entry.title,
            content=entry.content,
            tags=list(entry.tags),
            source_type=entry.source_type,
            source_uri=entry.source_uri,
            document_id=entry.document_id,
            document_title=entry.document_title,
            page_number=entry.page_number,
            chunk_index=entry.chunk_index,
            chunk_count=entry.chunk_count,
            source_chars=entry.source_chars,
            embedding=list(entry.embedding),
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )

    def to_domain(self) -> KnowledgeEntry:
        return KnowledgeEntry(
            id=str(self.id),
            title=self.title,
            content=self.content,
            tags=list(self.tags or []),
            source_type=self.source_type,
            source_uri=self.source_uri,
            document_id=self.document_id,
            document_title=self.document_title,
            page_number=self.page_number,
            chunk_index=self.chunk_index,
            chunk_count=self.chunk_count,
            source_chars=self.source_chars,
            embedding=list(self.embedding or []),
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class IdentityRecord(DatabaseBase):
    __tablename__ = "knowledge_engrams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    avatar: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    color_hex: Mapped[str] = mapped_column(String(32), nullable=False, default="#00ff41")
    intellectual_profile: Mapped[str] = mapped_column(String(255), nullable=False, default="General")
    behavior_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    meta_rule: Mapped[str] = mapped_column(Text, nullable=False, default="Stay consistent with the selected identity.")
    dialogue_examples: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    backstory: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    @classmethod
    def from_domain(cls, identity: Identity) -> "IdentityRecord":
        return cls(
            id=str(identity.id),
            name=identity.name,
            avatar=identity.avatar,
            color_hex=identity.color_hex,
            intellectual_profile=identity.intellectual_profile,
            behavior_prompt=identity.behavior_prompt,
            meta_rule=identity.meta_rule,
            dialogue_examples=list(identity.dialogue_examples),
            backstory=identity.backstory,
            created_at=identity.created_at,
            updated_at=identity.updated_at,
        )

    def to_domain(self) -> Identity:
        return Identity(
            id=str(self.id),
            name=self.name,
            avatar=self.avatar,
            color_hex=self.color_hex,
            intellectual_profile=self.intellectual_profile,
            behavior_prompt=self.behavior_prompt,
            meta_rule=self.meta_rule,
            dialogue_examples=list(self.dialogue_examples or []),
            backstory=self.backstory,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )