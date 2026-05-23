from __future__ import annotations

from dataclasses import dataclass

from app.core.events import EventChannel, EventKind, EventSpec


@dataclass(frozen=True)
class OperationsStatusRequest:
    limit: int = 10


@dataclass(frozen=True)
class OperationsAuditRequest:
    limit: int = 50


REQUEST_OPERATIONS_STATUS = EventSpec[OperationsStatusRequest, dict](
    name="operations.status.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=OperationsStatusRequest,
    output_type=dict,
)

REQUEST_OPERATIONS_AUDIT_LOG = EventSpec[OperationsAuditRequest, list](
    name="operations.audit_log.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=OperationsAuditRequest,
    output_type=list,
)


__all__ = [
    "OperationsAuditRequest",
    "OperationsStatusRequest",
    "REQUEST_OPERATIONS_AUDIT_LOG",
    "REQUEST_OPERATIONS_STATUS",
]