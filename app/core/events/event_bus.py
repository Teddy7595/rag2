from __future__ import annotations

from typing import Any

from app.core.events.event_envelope import EventEnvelope
from app.core.events.event_exceptions import EventContractError
from app.core.events.event_handler import PublishEventHandlerInterface, RequestEventHandlerInterface
from app.core.events.event_registry import EventRegistry
from app.core.events.event_router import EventRouter
from app.core.events.event_spec import EventChannel, EventKind, EventSpec, InputT, OutputT


def _is_instance_of_declared_type(value: Any, declared_type: type[Any] | None) -> bool:
    if declared_type is None:
        return True
    return isinstance(value, declared_type)


class EventBus:
    def __init__(
        self,
        registry: EventRegistry | None = None,
        router: EventRouter | None = None,
    ) -> None:
        self.registry = registry or EventRegistry()
        self.router = router or EventRouter(self.registry)

    def subscribe_request(
        self,
        spec: EventSpec[InputT, OutputT],
        handler: RequestEventHandlerInterface[InputT, OutputT],
    ) -> None:
        self.registry.register_request(spec, handler)

    def subscribe_publish(
        self,
        spec: EventSpec[InputT, Any],
        handler: PublishEventHandlerInterface[InputT],
    ) -> None:
        self.registry.register_publish(spec, handler)

    def subscribe_channel(
        self,
        channel: EventChannel,
        handler: PublishEventHandlerInterface[Any],
    ) -> None:
        self.registry.register_channel_listener(channel, handler)

    def build_envelope(
        self,
        spec: EventSpec[InputT, OutputT],
        payload: InputT,
        *,
        source_module: str,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        tenant_id: str | None = None,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventEnvelope[InputT]:
        if not _is_instance_of_declared_type(payload, spec.input_type):
            raise EventContractError(
                f"Payload for '{spec.name}' must be '{spec.input_type.__name__}'"
            )

        return EventEnvelope(
            spec=spec,
            payload=payload,
            source_module=source_module,
            correlation_id=correlation_id,
            causation_id=causation_id,
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            metadata=metadata or {},
        )

    def request(
        self,
        spec: EventSpec[InputT, OutputT],
        payload: InputT,
        *,
        source_module: str,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        tenant_id: str | None = None,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> OutputT:
        if spec.kind is not EventKind.REQUEST:
            raise EventContractError(f"Event '{spec.name}' is not a request event")

        envelope = self.build_envelope(
            spec,
            payload,
            source_module=source_module,
            correlation_id=correlation_id,
            causation_id=causation_id,
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            metadata=metadata,
        )
        result = self.router.route_request(envelope)

        if spec.output_type is not None and not _is_instance_of_declared_type(
            result, spec.output_type
        ):
            raise EventContractError(
                f"Output for '{spec.name}' must be '{spec.output_type.__name__}'"
            )

        return result

    def publish(
        self,
        spec: EventSpec[InputT, Any],
        payload: InputT,
        *,
        source_module: str,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        tenant_id: str | None = None,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if spec.kind is not EventKind.PUBLISH:
            raise EventContractError(f"Event '{spec.name}' is not a publish event")

        envelope = self.build_envelope(
            spec,
            payload,
            source_module=source_module,
            correlation_id=correlation_id,
            causation_id=causation_id,
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            metadata=metadata,
        )
        self.router.route_publish(envelope)


event_bus: EventBus | None = None


def init_event_bus(bus: EventBus) -> None:
    global event_bus
    event_bus = bus


def get_event_bus() -> EventBus:
    if event_bus is None:
        raise RuntimeError("EventBus not initialized. Call init_event_bus() from bootstrap.")
    return event_bus