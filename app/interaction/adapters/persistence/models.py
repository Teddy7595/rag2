from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import DatabaseBase
from app.interaction.domain import ConversationMessage


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConversationMessageRecord(DatabaseBase):
    __tablename__ = "interaction_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    author: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(String(64), nullable=False, default="chat", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    @classmethod
    def from_domain(cls, message: ConversationMessage) -> "ConversationMessageRecord":
        return cls(
            id=str(message.id),
            author=message.author,
            content=message.content,
            channel=message.channel,
            created_at=message.created_at,
            updated_at=message.updated_at,
        )

    def to_domain(self) -> ConversationMessage:
        return ConversationMessage(
            id=str(self.id),
            author=self.author,
            content=self.content,
            channel=self.channel,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )