from __future__ import annotations

from sqlalchemy import func, select

from app.core.database import DatabaseManager
from app.operations.adapters.persistence.models import OperationAuditEntryRecord
from app.operations.application.ports import AuditLogRepositoryPort
from app.operations.domain import OperationAuditEntry


class SqlAlchemyAuditLogRepository(AuditLogRepositoryPort):
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def save(self, entry: OperationAuditEntry) -> OperationAuditEntry:
        record = OperationAuditEntryRecord.from_domain(entry)
        with self.database.session_scope() as session:
            persisted = session.merge(record)
            session.flush()
            return persisted.to_domain()

    def list_recent(self, limit: int = 50) -> list[OperationAuditEntry]:
        if limit <= 0:
            return []

        with self.database.session_factory() as session:
            statement = (
                select(OperationAuditEntryRecord)
                .order_by(OperationAuditEntryRecord.created_at.desc(), OperationAuditEntryRecord.id.desc())
                .limit(limit)
            )
            records = session.scalars(statement).all()
            return [record.to_domain() for record in records]

    def count(self) -> int:
        with self.database.session_factory() as session:
            total = session.scalar(select(func.count()).select_from(OperationAuditEntryRecord))
            return int(total or 0)

    def event_counts(self) -> dict[str, int]:
        with self.database.session_factory() as session:
            statement = (
                select(OperationAuditEntryRecord.event_name, func.count())
                .group_by(OperationAuditEntryRecord.event_name)
                .order_by(OperationAuditEntryRecord.event_name.asc())
            )
            rows = session.execute(statement).all()
            return {event_name: int(total) for event_name, total in rows}