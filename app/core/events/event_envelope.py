from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar
from uuid import uuid4

from app.core.events.event_spec import EventSpec


PayloadT = TypeVar("PayloadT")


@dataclass(frozen=True)
class EventEnvelope(Generic[PayloadT]):
    spec: EventSpec[PayloadT, Any]
    payload: PayloadT
    source_module: str
    correlation_id: str | None = None
    causation_id: str | None = None
    tenant_id: str | None = None
    aggregate_type: str | None = None
    aggregate_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))