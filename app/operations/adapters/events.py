from fastapi import FastAPI

from app.core.app_context import get_app_context_from_app
from app.core.events import EventChannel, EventEnvelope


def register_operations_event_handlers(app: FastAPI) -> None:
    from app.operations.application.service import OperationsService
    from app.operations.events import REQUEST_OPERATIONS_AUDIT_LOG
    from app.operations.events import REQUEST_OPERATIONS_SAGA_COMMAND_APPEND
    from app.operations.events import REQUEST_OPERATIONS_SAGA_DELETE
    from app.operations.events import REQUEST_OPERATIONS_SAGA_DETAIL
    from app.operations.events import REQUEST_OPERATIONS_SAGA_LIST
    from app.operations.events import REQUEST_OPERATIONS_SAGA_START
    from app.operations.events import REQUEST_OPERATIONS_SAGA_UPDATE
    from app.operations.events import REQUEST_OPERATIONS_STATUS

    context = get_app_context_from_app(app)
    service = context.services.get("operations")
    if not isinstance(service, OperationsService):
        raise RuntimeError("Operations service not registered")

    def handle_status(envelope: EventEnvelope[object]) -> dict[str, object]:
        return service.status(envelope.payload)

    def handle_audit_log(envelope: EventEnvelope[object]) -> list[dict[str, object]]:
        return service.list_audit_log(envelope.payload)

    def handle_saga_list(envelope: EventEnvelope[object]) -> list[dict[str, object]]:
        return service.list_sagas(envelope.payload)

    def handle_saga_detail(envelope: EventEnvelope[object]) -> dict[str, object]:
        return service.get_saga(envelope.payload)

    def handle_saga_start(envelope: EventEnvelope[object]) -> dict[str, object]:
        return service.start_saga(envelope.payload)

    def handle_saga_command_append(envelope: EventEnvelope[object]) -> dict[str, object]:
        return service.append_saga_command(envelope.payload)

    def handle_saga_update(envelope: EventEnvelope[object]) -> dict[str, object]:
        return service.update_saga(envelope.payload)

    def handle_saga_delete(envelope: EventEnvelope[object]) -> dict[str, object]:
        return service.delete_saga(envelope.payload)

    context.event_bus.subscribe_request(REQUEST_OPERATIONS_STATUS, handle_status)
    context.event_bus.subscribe_request(REQUEST_OPERATIONS_AUDIT_LOG, handle_audit_log)
    context.event_bus.subscribe_request(REQUEST_OPERATIONS_SAGA_LIST, handle_saga_list)
    context.event_bus.subscribe_request(REQUEST_OPERATIONS_SAGA_DETAIL, handle_saga_detail)
    context.event_bus.subscribe_request(REQUEST_OPERATIONS_SAGA_START, handle_saga_start)
    context.event_bus.subscribe_request(REQUEST_OPERATIONS_SAGA_COMMAND_APPEND, handle_saga_command_append)
    context.event_bus.subscribe_request(REQUEST_OPERATIONS_SAGA_UPDATE, handle_saga_update)
    context.event_bus.subscribe_request(REQUEST_OPERATIONS_SAGA_DELETE, handle_saga_delete)
    context.event_bus.subscribe_channel(EventChannel.DOMAIN, service.capture_domain_event)