from __future__ import annotations

from typing import Any, Generic, TypeVar

from app.core.events.event_bus import EventBus, get_event_bus
from app.core.events.event_spec import EventSpec


PayloadT = TypeVar("PayloadT")
OutputT = TypeVar("OutputT")


class EventPublisher(Generic[PayloadT]):
    def __init__(self, source_module: str, bus: EventBus | None = None) -> None:
        self.source_module = source_module
        self.bus = bus or get_event_bus()

    def request(
        self,
        spec: EventSpec[PayloadT, OutputT],
        payload: PayloadT,
        **kwargs: Any,
    ) -> OutputT:
        return self.bus.request(spec, payload, source_module=self.source_module, **kwargs)

    def publish(
        self,
        spec: EventSpec[PayloadT, Any],
        payload: PayloadT,
        **kwargs: Any,
    ) -> None:
        self.bus.publish(spec, payload, source_module=self.source_module, **kwargs)