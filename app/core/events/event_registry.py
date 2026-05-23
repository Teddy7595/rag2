from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.core.events.event_exceptions import EventContractError
from app.core.events.event_handler import PublishEventHandlerInterface, RequestEventHandlerInterface
from app.core.events.event_spec import EventChannel, EventKind, EventSpec


class EventRegistry:
    def __init__(self) -> None:
        self._request_handlers: dict[str, RequestEventHandlerInterface[Any, Any]] = {}
        self._publish_handlers: dict[str, list[PublishEventHandlerInterface[Any]]] = defaultdict(list)
        self._channel_handlers: dict[EventChannel, list[PublishEventHandlerInterface[Any]]] = defaultdict(list)

    def register_request(
        self,
        spec: EventSpec[Any, Any],
        handler: RequestEventHandlerInterface[Any, Any],
    ) -> None:
        if spec.kind is not EventKind.REQUEST:
            raise EventContractError(f"Event '{spec.name}' is not a request event")
        if spec.name in self._request_handlers:
            raise EventContractError(f"Request event '{spec.name}' already has a handler")
        self._request_handlers[spec.name] = handler

    def register_publish(
        self,
        spec: EventSpec[Any, Any],
        handler: PublishEventHandlerInterface[Any],
    ) -> None:
        if spec.kind is not EventKind.PUBLISH:
            raise EventContractError(f"Event '{spec.name}' is not a publish event")
        self._publish_handlers[spec.name].append(handler)

    def register_channel_listener(
        self,
        channel: EventChannel,
        handler: PublishEventHandlerInterface[Any],
    ) -> None:
        self._channel_handlers[channel].append(handler)

    def get_request_handler(self, event_name: str) -> RequestEventHandlerInterface[Any, Any] | None:
        return self._request_handlers.get(event_name)

    def get_publish_handlers(self, event_name: str) -> list[PublishEventHandlerInterface[Any]]:
        return list(self._publish_handlers.get(event_name, []))

    def get_channel_handlers(self, channel: EventChannel) -> list[PublishEventHandlerInterface[Any]]:
        return list(self._channel_handlers.get(channel, []))