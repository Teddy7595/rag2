from fastapi import FastAPI

from app.core.app_context import get_app_context_from_app
from app.core.events import EventEnvelope
from app.interaction.application import InteractionService
from app.interaction.events import (
    REQUEST_INTERACTION_MESSAGE_RECORD,
    REQUEST_INTERACTION_MESSAGES,
    REQUEST_INTERACTION_SESSION_MEMORY,
    REQUEST_INTERACTION_SESSION_CONDITIONS,
    REQUEST_INTERACTION_SESSION_CONDITIONS_SET,
    REQUEST_INTERACTION_SESSION_TOPIC_GRAPH,
    REQUEST_INTERACTION_TURN_METRICS,
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

    def handle_session_memory(envelope: EventEnvelope[object]) -> dict[str, object]:
        return service.session_memory(envelope.payload)

    def handle_session_topic_graph(envelope: EventEnvelope[object]) -> dict[str, object]:
        return service.session_topic_graph(envelope.payload)

    def handle_turn_metrics(envelope: EventEnvelope[object]) -> list[dict[str, object]]:
        return service.turn_metrics(envelope.payload)

    def handle_session_conditions(envelope: EventEnvelope[object]) -> dict[str, object]:
        return service.session_conditions(envelope.payload)

    def handle_session_conditions_set(envelope: EventEnvelope[object]) -> dict[str, object]:
        return service.set_session_conditions(envelope.payload)

    context.event_bus.subscribe_request(REQUEST_INTERACTION_SUMMARY, handle_summary)
    context.event_bus.subscribe_request(REQUEST_INTERACTION_MESSAGES, handle_list)
    context.event_bus.subscribe_request(REQUEST_INTERACTION_MESSAGE_RECORD, handle_record)
    context.event_bus.subscribe_request(REQUEST_INTERACTION_SESSION_MEMORY, handle_session_memory)
    context.event_bus.subscribe_request(REQUEST_INTERACTION_SESSION_CONDITIONS, handle_session_conditions)
    context.event_bus.subscribe_request(REQUEST_INTERACTION_SESSION_CONDITIONS_SET, handle_session_conditions_set)
    context.event_bus.subscribe_request(REQUEST_INTERACTION_SESSION_TOPIC_GRAPH, handle_session_topic_graph)
    context.event_bus.subscribe_request(REQUEST_INTERACTION_TURN_METRICS, handle_turn_metrics)