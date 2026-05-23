from fastapi import FastAPI

from app.core.app_context import get_app_context_from_app
from app.core.events import EventEnvelope
from app.interaction.application import InteractionService
from app.interaction.events import (
    REQUEST_INTERACTION_MESSAGE_RECORD,
    REQUEST_INTERACTION_MESSAGES,
    REQUEST_INTERACTION_SUMMARY,
)


def register_interaction_event_handlers(app: FastAPI) -> None:
    context = get_app_context_from_app(app)
    service = context.services.get("interaction")
    if not isinstance(service, InteractionService):
        raise RuntimeError("Interaction service not registered")

    def handle_summary(envelope: EventEnvelope[object]) -> dict[str, object]:
        return service.summary(envelope.payload)

    def handle_list(envelope: EventEnvelope[object]) -> list[dict[str, object]]:
        return service.list_messages(envelope.payload)

    def handle_record(envelope: EventEnvelope[object]) -> dict[str, object]:
        return service.record_message(envelope.payload)

    context.event_bus.subscribe_request(REQUEST_INTERACTION_SUMMARY, handle_summary)
    context.event_bus.subscribe_request(REQUEST_INTERACTION_MESSAGES, handle_list)
    context.event_bus.subscribe_request(REQUEST_INTERACTION_MESSAGE_RECORD, handle_record)