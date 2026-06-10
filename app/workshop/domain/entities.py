from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WorkshopSession:
    id: str
    title: str
    engram_id: str
    chat_session_id: str
    status: str  # "active" | "closed" | "promoted"
    source_documents: list[dict]  # [{uri, title}]
    promoted_entry_ids: list[str]  # knowledge entry IDs added to main RAG from this workshop
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None

    @classmethod
    def new(cls, title: str, engram_id: str, chat_session_id: str) -> "WorkshopSession":
        now = _utcnow()
        return cls(
            id=str(uuid4()),
            title=title,
            engram_id=engram_id,
            chat_session_id=chat_session_id,
            status="active",
            source_documents=[],
            promoted_entry_ids=[],
            created_at=now,
            updated_at=now,
        )

    def source_uris(self) -> list[str]:
        return [str(doc.get("uri") or "") for doc in self.source_documents if doc.get("uri")]

    def touch(self) -> None:
        self.updated_at = _utcnow()

    def close(self) -> None:
        self.status = "closed"
        self.closed_at = _utcnow()
        self.touch()

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "engram_id": self.engram_id,
            "chat_session_id": self.chat_session_id,
            "status": self.status,
            "source_documents": self.source_documents,
            "promoted_entry_ids": self.promoted_entry_ids,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
        }
