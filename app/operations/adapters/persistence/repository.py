from __future__ import annotations

from sqlalchemy import func, select

from app.core.database import DatabaseManager
from app.operations.adapters.persistence.models import OperationAuditEntryRecord, SagaWorkflowRecord
from app.operations.application.ports import AuditLogRepositoryPort, SagaWorkflowRepositoryPort
from app.operations.domain import OperationAuditEntry, SagaWorkflow


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


class SqlAlchemySagaWorkflowRepository(SagaWorkflowRepositoryPort):
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def save(self, workflow: SagaWorkflow) -> SagaWorkflow:
        record = SagaWorkflowRecord.from_domain(workflow)
        with self.database.session_scope() as session:
            persisted = session.merge(record)
            session.flush()
            return persisted.to_domain()

    def get_by_id(self, saga_id: str) -> SagaWorkflow | None:
        with self.database.session_factory() as session:
            record = session.get(SagaWorkflowRecord, saga_id)
            return record.to_domain() if record else None

    def list_recent(self, limit: int = 20) -> list[SagaWorkflow]:
        if limit <= 0:
            return []

        with self.database.session_factory() as session:
            statement = (
                select(SagaWorkflowRecord)
                .order_by(SagaWorkflowRecord.created_at.desc(), SagaWorkflowRecord.id.desc())
                .limit(limit)
            )
            records = session.scalars(statement).all()
            return [record.to_domain() for record in reversed(records)]

    def delete(self, saga_id: str) -> bool:
        with self.database.session_scope() as session:
            record = session.get(SagaWorkflowRecord, saga_id)
            if not record:
                return False
            session.delete(record)
            session.flush()
            return True

    def count(self) -> int:
        with self.database.session_factory() as session:
            total = session.scalar(select(func.count()).select_from(SagaWorkflowRecord))
            return int(total or 0)