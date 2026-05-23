from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import DatabaseBase
from app.operations.domain import OperationAuditEntry
from app.operations.domain import SagaWorkflow


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OperationAuditEntryRecord(DatabaseBase):
    __tablename__ = "operation_audit_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_module: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    causation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    @classmethod
    def from_domain(cls, entry: OperationAuditEntry) -> "OperationAuditEntryRecord":
        return cls(
            id=str(entry.id),
            event_name=entry.event_name,
            source_module=entry.source_module,
            channel=entry.channel,
            payload=dict(entry.payload),
            correlation_id=entry.correlation_id,
            causation_id=entry.causation_id,
            event_metadata=dict(entry.metadata),
            created_at=entry.created_at,
        )

    def to_domain(self) -> OperationAuditEntry:
        return OperationAuditEntry(
            id=str(self.id),
            event_name=self.event_name,
            source_module=self.source_module,
            channel=self.channel,
            payload=dict(self.payload or {}),
            correlation_id=self.correlation_id,
            causation_id=self.causation_id,
            metadata=dict(self.event_metadata or {}),
            created_at=self.created_at,
        )


class SagaWorkflowRecord(DatabaseBase):
    __tablename__ = "operation_saga_workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    premise: Mapped[str] = mapped_column(String(4096), nullable=False, default="")
    summary: Mapped[str] = mapped_column(String(4096), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="active", index=True)
    world_building: Mapped[str] = mapped_column(String(8192), nullable=False, default="")
    command_history: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    act_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    @classmethod
    def from_domain(cls, workflow: SagaWorkflow) -> "SagaWorkflowRecord":
        return cls(
            id=str(workflow.id),
            title=workflow.title,
            premise=workflow.premise,
            summary=workflow.summary,
            status=workflow.status,
            world_building=workflow.world_building,
            command_history=list(workflow.command_history),
            act_history=list(workflow.act_history),
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
        )

    def to_domain(self) -> SagaWorkflow:
        return SagaWorkflow(
            id=str(self.id),
            title=self.title,
            premise=self.premise,
            summary=self.summary,
            status=self.status,
            world_building=self.world_building,
            command_history=list(self.command_history or []),
            act_history=list(self.act_history or []),
            created_at=self.created_at,
            updated_at=self.updated_at,
        )