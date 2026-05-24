from __future__ import annotations

from dataclasses import dataclass, field

from app.core.base_entity import BaseEntity


@dataclass
class KnowledgeEntry(BaseEntity):
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    source_type: str = "manual"
    source_uri: str = ""
    document_id: str = ""
    document_title: str = ""
    page_number: int | None = None
    chunk_index: int | None = None
    chunk_count: int | None = None
    source_chars: int = 0
    embedding: list[float] = field(default_factory=list)
    engram_id: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "tags": list(self.tags),
            "source_type": self.source_type,
            "source_uri": self.source_uri,
            "document_id": self.document_id,
            "document_title": self.document_title,
            "page_number": self.page_number,
            "chunk_index": self.chunk_index,
            "chunk_count": self.chunk_count,
            "source_chars": self.source_chars,
            "embedding": list(self.embedding),
            "engram_id": self.engram_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }