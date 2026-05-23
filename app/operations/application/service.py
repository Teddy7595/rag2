from __future__ import annotations

from typing import Any

from app.core.events import EventEnvelope
from app.operations.application.ports import AuditLogRepositoryPort
from app.operations.domain import OperationAuditEntry
from app.operations.events import OperationsAuditRequest, OperationsStatusRequest


class OperationsService:
    def __init__(self, repository: AuditLogRepositoryPort) -> None:
        self.repository = repository

    def capture_domain_event(self, envelope: EventEnvelope[Any]) -> None:
        self.repository.save(OperationAuditEntry.from_envelope(envelope))

    def status(self, request: OperationsStatusRequest) -> dict[str, object]:
        recent_entries = self.list_audit_log(OperationsAuditRequest(limit=request.limit))
        return {
            "captured_events": self.repository.count(),
            "recent_entries": recent_entries,
            "event_counts": self.repository.event_counts(),
        }

    def list_audit_log(self, request: OperationsAuditRequest) -> list[dict[str, object]]:
        if request.limit <= 0:
            return []
        entries = self.repository.list_recent(limit=request.limit)
        return [entry.as_dict() for entry in entries]