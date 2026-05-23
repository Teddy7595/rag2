from __future__ import annotations

from typing import Protocol, TypeVar

from app.core.events.event_envelope import EventEnvelope


InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class RequestEventHandlerInterface(Protocol[InputT, OutputT]): #type: ignore
    def __call__(self, envelope: EventEnvelope[InputT]) -> OutputT: ...


class PublishEventHandlerInterface(Protocol[InputT]):
    def __call__(self, envelope: EventEnvelope[InputT]) -> None: ...