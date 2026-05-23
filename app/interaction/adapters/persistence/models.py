from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Float, JSON, String, Text
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
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    @classmethod
    def from_domain(cls, message: ConversationMessage) -> "ConversationMessageRecord":
        return cls(
            id=str(message.id),
            author=message.author,
            content=message.content,
            channel=message.channel,
            session_id=message.session_id,
            created_at=message.created_at,
            updated_at=message.updated_at,
        )

    def to_domain(self) -> ConversationMessage:
        return ConversationMessage(
            id=str(self.id),
            author=self.author,
            content=self.content,
            channel=self.channel,
            session_id=self.session_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class SessionMemorySnapshotRecord(DatabaseBase):
    __tablename__ = "interaction_session_memory"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sliding_window_size: Mapped[int] = mapped_column(nullable=False, default=20)
    last_turn_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    coherence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)


class SessionTopicGraphRecord(DatabaseBase):
    __tablename__ = "interaction_session_topic_graph"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    primary_topic: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    secondary_topics: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    topic_states: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    edges: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)


class TurnCoherenceMetricRecord(DatabaseBase):
    __tablename__ = "interaction_turn_metrics"

    turn_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_input: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assistant_reply: Mapped[str] = mapped_column(Text, nullable=False, default="")
    primary_topic: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    secondary_topics: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    coherence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, index=True)
    context_trace: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)


class SessionConditionsRecord(DatabaseBase):
    __tablename__ = "interaction_session_conditions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_rules: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)