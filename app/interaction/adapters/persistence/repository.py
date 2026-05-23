from __future__ import annotations

from sqlalchemy import func, select

from app.core.database import DatabaseManager
from app.interaction.adapters.persistence.models import ConversationMessageRecord
from app.interaction.application.ports import InteractionMessageRepositoryPort
from app.interaction.domain import ConversationMessage


class SqlAlchemyInteractionMessageRepository(InteractionMessageRepositoryPort):
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def save(self, message: ConversationMessage) -> ConversationMessage:
        record = ConversationMessageRecord.from_domain(message)
        with self.database.session_scope() as session:
            persisted = session.merge(record)
            session.flush()
            return persisted.to_domain()

    def list_recent(self, limit: int = 20) -> list[ConversationMessage]:
        if limit <= 0:
            return []

        with self.database.session_factory() as session:
            statement = (
                select(ConversationMessageRecord)
                .order_by(ConversationMessageRecord.created_at.desc(), ConversationMessageRecord.id.desc())
                .limit(limit)
            )
            records = session.scalars(statement).all()
            return [record.to_domain() for record in reversed(records)]

    def count(self) -> int:
        with self.database.session_factory() as session:
            total = session.scalar(select(func.count()).select_from(ConversationMessageRecord))
            return int(total or 0)

    def channel_counts(self) -> dict[str, int]:
        with self.database.session_factory() as session:
            statement = (
                select(ConversationMessageRecord.channel, func.count())
                .group_by(ConversationMessageRecord.channel)
                .order_by(ConversationMessageRecord.channel.asc())
            )
            rows = session.execute(statement).all()
            return {channel: int(total) for channel, total in rows}