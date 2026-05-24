from __future__ import annotations

from sqlalchemy import func, or_, select

from app.core.database import DatabaseManager
from app.knowledge.adapters.persistence.models import IdentityRecord, KnowledgeEntryRecord
from app.knowledge.application.ports import EngramRepositoryPort, KnowledgeRepositoryPort
from app.knowledge.domain import Identity, KnowledgeEntry


class SqlAlchemyKnowledgeRepository(KnowledgeRepositoryPort):
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def save(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        record = KnowledgeEntryRecord.from_domain(entry)
        with self.database.session_scope() as session:
            persisted = session.merge(record)
            session.flush()
            return persisted.to_domain()

    def list_all(self) -> list[KnowledgeEntry]:
        with self.database.session_factory() as session:
            statement = select(KnowledgeEntryRecord).order_by(KnowledgeEntryRecord.created_at.asc(), KnowledgeEntryRecord.id.asc())
            records = session.scalars(statement).all()
            return [record.to_domain() for record in records]

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

    def list_by_engram(self, engram_id: str) -> list[KnowledgeEntry]:
        """Return entries scoped to the given engram plus global (NULL engram_id) entries."""
        with self.database.session_factory() as session:
            statement = (
                select(KnowledgeEntryRecord)
                .where(
                    or_(
                        KnowledgeEntryRecord.engram_id == engram_id,
                        KnowledgeEntryRecord.engram_id.is_(None),
                    )
                )
                .order_by(KnowledgeEntryRecord.created_at.asc(), KnowledgeEntryRecord.id.asc())
            )
            records = session.scalars(statement).all()
            return [record.to_domain() for record in records]

    def count(self) -> int:
        with self.database.session_factory() as session:
            total = session.scalar(select(func.count()).select_from(KnowledgeEntryRecord))
            return int(total or 0)


class SqlAlchemyEngramRepository(EngramRepositoryPort):
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def save(self, identity: Identity) -> Identity:
        record = IdentityRecord.from_domain(identity)
        with self.database.session_scope() as session:
            persisted = session.merge(record)
            session.flush()
            return persisted.to_domain()

    def get_by_id(self, engram_id: str) -> Identity | None:
        with self.database.session_factory() as session:
            record = session.get(IdentityRecord, engram_id)
            return record.to_domain() if record else None

    def list_all(self) -> list[Identity]:
        with self.database.session_factory() as session:
            statement = select(IdentityRecord).order_by(IdentityRecord.created_at.asc(), IdentityRecord.id.asc())
            records = session.scalars(statement).all()
            return [record.to_domain() for record in records]

    def list_recent(self, limit: int = 20) -> list[Identity]:
        if limit <= 0:
            return []

        with self.database.session_factory() as session:
            statement = (
                select(IdentityRecord)
                .order_by(IdentityRecord.created_at.desc(), IdentityRecord.id.desc())
                .limit(limit)
            )
            records = session.scalars(statement).all()
            return [record.to_domain() for record in reversed(records)]

    def delete(self, engram_id: str) -> bool:
        with self.database.session_scope() as session:
            record = session.get(IdentityRecord, engram_id)
            if not record:
                return False
            session.delete(record)
            session.flush()
            return True

    def count(self) -> int:
        with self.database.session_factory() as session:
            total = session.scalar(select(func.count()).select_from(IdentityRecord))
            return int(total or 0)