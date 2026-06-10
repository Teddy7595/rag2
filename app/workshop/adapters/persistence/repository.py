from __future__ import annotations

from sqlalchemy import select

from app.core.database import DatabaseManager
from app.workshop.adapters.persistence.models import WorkshopSessionRecord
from app.workshop.application.ports import WorkshopRepositoryPort
from app.workshop.domain.entities import WorkshopSession


class SqlAlchemyWorkshopRepository(WorkshopRepositoryPort):
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def save(self, ws: WorkshopSession) -> WorkshopSession:
        record = WorkshopSessionRecord.from_domain(ws)
        with self.database.session_scope() as session:
            persisted = session.merge(record)
            session.flush()
            return persisted.to_domain()

    def get_by_id(self, workshop_id: str) -> WorkshopSession | None:
        with self.database.session_factory() as session:
            record = session.get(WorkshopSessionRecord, workshop_id)
            return record.to_domain() if record else None

    def get_by_chat_session(self, chat_session_id: str) -> WorkshopSession | None:
        with self.database.session_factory() as session:
            stmt = select(WorkshopSessionRecord).where(
                WorkshopSessionRecord.chat_session_id == chat_session_id
            )
            record = session.scalars(stmt).first()
            return record.to_domain() if record else None

    def list_recent(self, limit: int = 20) -> list[WorkshopSession]:
        if limit <= 0:
            return []
        with self.database.session_factory() as session:
            stmt = (
                select(WorkshopSessionRecord)
                .order_by(WorkshopSessionRecord.created_at.desc(), WorkshopSessionRecord.id.desc())
                .limit(limit)
            )
            records = session.scalars(stmt).all()
            return [r.to_domain() for r in reversed(records)]

    def delete(self, workshop_id: str) -> bool:
        with self.database.session_scope() as session:
            record = session.get(WorkshopSessionRecord, workshop_id)
            if not record:
                return False
            session.delete(record)
            session.flush()
            return True
