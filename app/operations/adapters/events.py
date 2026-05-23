from fastapi import FastAPI

from app.core.app_context import get_app_context_from_app
from app.core.events import EventChannel, EventEnvelope
from app.operations.application import OperationsService
from app.operations.events import REQUEST_OPERATIONS_AUDIT_LOG, REQUEST_OPERATIONS_STATUS


def register_operations_event_handlers(app: FastAPI) -> None:
    context = get_app_context_from_app(app)
    service = context.services.get("operations")
    if not isinstance(service, OperationsService):
        raise RuntimeError("Operations service not registered")

    def handle_status(envelope: EventEnvelope[object]) -> dict[str, object]:
        return service.status(envelope.payload)

    def handle_audit_log(envelope: EventEnvelope[object]) -> list[dict[str, object]]:
        return service.list_audit_log(envelope.payload)

    context.event_bus.subscribe_request(REQUEST_OPERATIONS_STATUS, handle_status)
    context.event_bus.subscribe_request(REQUEST_OPERATIONS_AUDIT_LOG, handle_audit_log)
    context.event_bus.subscribe_channel(EventChannel.DOMAIN, service.capture_domain_event)