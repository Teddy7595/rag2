from __future__ import annotations

from sqlalchemy import delete, func, select

from app.core.database import DatabaseManager
from app.knowledge.adapters.persistence.models import AffectiveStateRecord, IdentityRecord, KnowledgeEntryRecord, utcnow
from app.knowledge.application.ports import AffectiveStateRepositoryPort, EngramRepositoryPort, KnowledgeRepositoryPort
from app.knowledge.domain import AffectiveState, Identity, KnowledgeEntry


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

    def list_by_sources(self, source_uris: list[str]) -> list[KnowledgeEntry]:
        if not source_uris:
            return []
        with self.database.session_factory() as session:
            statement = (
                select(KnowledgeEntryRecord)
                .where(KnowledgeEntryRecord.source_uri.in_(source_uris))
                .order_by(KnowledgeEntryRecord.created_at.asc(), KnowledgeEntryRecord.id.asc())
            )
            records = session.scalars(statement).all()
            return [record.to_domain() for record in records]

    def list_by_document_id(self, document_id: str) -> list[KnowledgeEntry]:
        if not document_id:
            return []
        with self.database.session_factory() as session:
            statement = (
                select(KnowledgeEntryRecord)
                .where(KnowledgeEntryRecord.document_id == document_id)
                .order_by(KnowledgeEntryRecord.page_number.asc().nulls_first(), KnowledgeEntryRecord.chunk_index.asc().nulls_first())
            )
            records = session.scalars(statement).all()
            return [record.to_domain() for record in records]

    def delete_by_document_id(self, document_id: str) -> int:
        if not document_id:
            return 0
        with self.database.session_scope() as session:
            result = session.execute(
                delete(KnowledgeEntryRecord).where(KnowledgeEntryRecord.document_id == document_id)
            )
            return int(result.rowcount or 0)

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


class SqlAlchemyAffectiveStateRepository(AffectiveStateRepositoryPort):
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def get(self, engram_id: str) -> AffectiveState | None:
        with self.database.session_factory() as session:
            record = session.get(AffectiveStateRecord, engram_id)
            if not record:
                return None
            return AffectiveState(
                engram_id=record.engram_id,
                pleasure=record.pleasure,
                arousal=record.arousal,
                dominance=record.dominance,
                updated_at=record.updated_at,
            )

    def upsert(self, state: AffectiveState) -> AffectiveState:
        record = AffectiveStateRecord(
            engram_id=state.engram_id,
            pleasure=state.pleasure,
            arousal=state.arousal,
            dominance=state.dominance,
            updated_at=state.updated_at or utcnow(),
        )
        with self.database.session_scope() as session:
            persisted = session.merge(record)
            session.flush()
            return AffectiveState(
                engram_id=persisted.engram_id,
                pleasure=persisted.pleasure,
                arousal=persisted.arousal,
                dominance=persisted.dominance,
                updated_at=persisted.updated_at,
            )