from __future__ import annotations

from typing import Any

from app.core.events.event_envelope import EventEnvelope
from app.core.events.event_exceptions import EventRoutingError
from app.core.events.event_registry import EventRegistry


class EventRouter:
    def __init__(self, registry: EventRegistry):
        self.registry = registry

    def route_request(self, envelope: EventEnvelope[Any]) -> Any:
        handler = self.registry.get_request_handler(envelope.spec.name)
        if handler is None:
            raise EventRoutingError(f"No request handler registered for '{envelope.spec.name}'")
        return handler(envelope)

    def route_publish(self, envelope: EventEnvelope[Any]) -> None:
        handlers = self.registry.get_publish_handlers(envelope.spec.name)
        channel_handlers = self.registry.get_channel_handlers(envelope.spec.channel)
        for handler in [*handlers, *channel_handlers]:
            handler(envelope)