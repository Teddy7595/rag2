from __future__ import annotations

from typing import Protocol

from app.operations.domain import OperationAuditEntry


class AuditLogRepositoryPort(Protocol):
    def save(self, entry: OperationAuditEntry) -> OperationAuditEntry: ...

    def list_recent(self, limit: int = 50) -> list[OperationAuditEntry]: ...

    def count(self) -> int: ...

    def event_counts(self) -> dict[str, int]: ...