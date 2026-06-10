from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import DatabaseBase
from app.workshop.domain.entities import WorkshopSession


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkshopSessionRecord(DatabaseBase):
    __tablename__ = "workshop_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    engram_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    chat_session_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    source_documents: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    promoted_entry_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @classmethod
    def from_domain(cls, ws: WorkshopSession) -> "WorkshopSessionRecord":
        return cls(
            id=ws.id,
            title=ws.title,
            engram_id=ws.engram_id,
            chat_session_id=ws.chat_session_id,
            status=ws.status,
            source_documents=list(ws.source_documents),
            promoted_entry_ids=list(ws.promoted_entry_ids),
            created_at=ws.created_at,
            updated_at=ws.updated_at,
            closed_at=ws.closed_at,
        )

    def to_domain(self) -> WorkshopSession:
        return WorkshopSession(
            id=str(self.id),
            title=self.title,
            engram_id=self.engram_id,
            chat_session_id=self.chat_session_id,
            status=self.status,
            source_documents=list(self.source_documents or []),
            promoted_entry_ids=list(self.promoted_entry_ids or []),
            created_at=self.created_at,
            updated_at=self.updated_at,
            closed_at=self.closed_at,
        )
