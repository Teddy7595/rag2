from __future__ import annotations

from app.core.events import EventChannel, EventKind, EventSpec


class OperationsStatusRequest:
    def __init__(self, limit: int = 10) -> None:
        self.limit = limit


class OperationsAuditRequest:
    def __init__(self, limit: int = 50) -> None:
        self.limit = limit


class OperationsSagaListRequest:
    def __init__(self, limit: int = 20, statuses: tuple[str, ...] | None = None) -> None:
        self.limit = limit
        self.statuses = statuses


class OperationsSagaDetailRequest:
    def __init__(self, saga_id: str) -> None:
        self.saga_id = saga_id


class OperationsSagaStartRequest:
    def __init__(
        self,
        title: str,
        premise: str = "",
        summary: str = "",
        world_building: str = "",
        initial_command: str = "",
    ) -> None:
        self.title = title
        self.premise = premise
        self.summary = summary
        self.world_building = world_building
        self.initial_command = initial_command


class OperationsSagaCommandAppendRequest:
    def __init__(self, saga_id: str, command: str, note: str = "") -> None:
        self.saga_id = saga_id
        self.command = command
        self.note = note


class OperationsSagaUpdateRequest:
    def __init__(
        self,
        saga_id: str,
        title: str | None = None,
        premise: str | None = None,
        summary: str | None = None,
        status: str | None = None,
        world_building: str | None = None,
    ) -> None:
        self.saga_id = saga_id
        self.title = title
        self.premise = premise
        self.summary = summary
        self.status = status
        self.world_building = world_building


class OperationsSagaDeleteRequest:
    def __init__(self, saga_id: str) -> None:
        self.saga_id = saga_id


class OperationsSagaDebateRequest:
    def __init__(
        self,
        saga_id: str,
        topic: str,
        note: str = "",
        identity_name: str = "System",
        persist_memory: bool = True,
    ) -> None:
        self.saga_id = saga_id
        self.topic = topic
        self.note = note
        self.identity_name = identity_name
        self.persist_memory = persist_memory


class OperationsSagaConsistencyRequest:
    def __init__(self, saga_id: str) -> None:
        self.saga_id = saga_id


class OperationsSagaRetconRequest:
    def __init__(self, saga_id: str, apply: bool = False) -> None:
        self.saga_id = saga_id
        self.apply = apply


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

REQUEST_OPERATIONS_SAGA_LIST = EventSpec[OperationsSagaListRequest, list](
    name="operations.sagas.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=OperationsSagaListRequest,
    output_type=list,
)

REQUEST_OPERATIONS_SAGA_DETAIL = EventSpec[OperationsSagaDetailRequest, dict](
    name="operations.saga.detail.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=OperationsSagaDetailRequest,
    output_type=dict,
)

REQUEST_OPERATIONS_SAGA_START = EventSpec[OperationsSagaStartRequest, dict](
    name="operations.saga.start.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=OperationsSagaStartRequest,
    output_type=dict,
)

REQUEST_OPERATIONS_SAGA_COMMAND_APPEND = EventSpec[OperationsSagaCommandAppendRequest, dict](
    name="operations.saga.command.append.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=OperationsSagaCommandAppendRequest,
    output_type=dict,
)

REQUEST_OPERATIONS_SAGA_UPDATE = EventSpec[OperationsSagaUpdateRequest, dict](
    name="operations.saga.update.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=OperationsSagaUpdateRequest,
    output_type=dict,
)

REQUEST_OPERATIONS_SAGA_DELETE = EventSpec[OperationsSagaDeleteRequest, dict](
    name="operations.saga.delete.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=OperationsSagaDeleteRequest,
    output_type=dict,
)

REQUEST_OPERATIONS_SAGA_DEBATE = EventSpec[OperationsSagaDebateRequest, dict](
    name="operations.saga.debate.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=OperationsSagaDebateRequest,
    output_type=dict,
)

REQUEST_OPERATIONS_SAGA_CONSISTENCY = EventSpec[OperationsSagaConsistencyRequest, dict](
    name="operations.saga.consistency.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=OperationsSagaConsistencyRequest,
    output_type=dict,
)

REQUEST_OPERATIONS_SAGA_RETCON = EventSpec[OperationsSagaRetconRequest, dict](
    name="operations.saga.retcon.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=OperationsSagaRetconRequest,
    output_type=dict,
)

PUBLISH_OPERATIONS_SAGA_STARTED = EventSpec[dict, dict](
    name="operations.saga.started",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)

PUBLISH_OPERATIONS_SAGA_COMMAND_APPENDED = EventSpec[dict, dict](
    name="operations.saga.command.appended",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)

PUBLISH_OPERATIONS_SAGA_UPDATED = EventSpec[dict, dict](
    name="operations.saga.updated",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)

PUBLISH_OPERATIONS_SAGA_DELETED = EventSpec[dict, dict](
    name="operations.saga.deleted",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)

PUBLISH_OPERATIONS_SAGA_DEBATED = EventSpec[dict, dict](
    name="operations.saga.debated",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)


__all__ = [
    "OperationsAuditRequest",
    "OperationsStatusRequest",
    "OperationsSagaCommandAppendRequest",
    "OperationsSagaDeleteRequest",
    "OperationsSagaDebateRequest",
    "OperationsSagaConsistencyRequest",
    "OperationsSagaDetailRequest",
        "OperationsSagaRetconRequest",
    "OperationsSagaListRequest",
    "OperationsSagaStartRequest",
    "OperationsSagaUpdateRequest",
    "PUBLISH_OPERATIONS_SAGA_COMMAND_APPENDED",
    "PUBLISH_OPERATIONS_SAGA_DELETED",
    "PUBLISH_OPERATIONS_SAGA_DEBATED",
    "PUBLISH_OPERATIONS_SAGA_STARTED",
    "PUBLISH_OPERATIONS_SAGA_UPDATED",
    "REQUEST_OPERATIONS_AUDIT_LOG",
    "REQUEST_OPERATIONS_SAGA_COMMAND_APPEND",
    "REQUEST_OPERATIONS_SAGA_CONSISTENCY",
    "REQUEST_OPERATIONS_SAGA_DEBATE",
        "REQUEST_OPERATIONS_SAGA_RETCON",
    "REQUEST_OPERATIONS_SAGA_DELETE",
    "REQUEST_OPERATIONS_SAGA_DETAIL",
    "REQUEST_OPERATIONS_SAGA_LIST",
    "REQUEST_OPERATIONS_SAGA_START",
    "REQUEST_OPERATIONS_SAGA_UPDATE",
    "REQUEST_OPERATIONS_STATUS",
]