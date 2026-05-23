from __future__ import annotations

from sqlalchemy import func, select

from app.core.database import DatabaseManager
from app.knowledge.adapters.persistence.models import KnowledgeEntryRecord
from app.knowledge.application.ports import KnowledgeRepositoryPort
from app.knowledge.domain import KnowledgeEntry


class SqlAlchemyKnowledgeRepository(KnowledgeRepositoryPort):
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def save(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        record = KnowledgeEntryRecord.from_domain(entry)
        with self.database.session_scope() as session:
            persisted = session.merge(record)
            session.flush()
            return persisted.to_domain()

    def list_recent(self, limit: int = 20) -> list[KnowledgeEntry]:
        if limit <= 0:
            return []

        with self.database.session_factory() as session:
            statement = (
                select(KnowledgeEntryRecord)
                .order_by(KnowledgeEntryRecord.created_at.desc(), KnowledgeEntryRecord.id.desc())
                .limit(limit)
            )
            records = session.scalars(statement).all()
            return [record.to_domain() for record in records]

    def count(self) -> int:
        with self.database.session_factory() as session:
            total = session.scalar(select(func.count()).select_from(KnowledgeEntryRecord))
            return int(total or 0)