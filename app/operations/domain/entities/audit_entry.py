from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.base_entity import BaseEntity
from app.core.events import EventEnvelope


@dataclass
class OperationAuditEntry(BaseEntity):
    event_name: str
    source_module: str
    channel: str
    payload: dict[str, Any]
    correlation_id: str | None = None
    causation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_envelope(cls, envelope: EventEnvelope[Any]) -> "OperationAuditEntry":
        payload = envelope.payload if isinstance(envelope.payload, dict) else {"value": envelope.payload}
        return cls(
            event_name=envelope.spec.name,
            source_module=envelope.source_module,
            channel=envelope.spec.channel.value,
            payload=payload,
            correlation_id=envelope.correlation_id,
            causation_id=envelope.causation_id,
            metadata=dict(envelope.metadata),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_name": self.event_name,
            "source_module": self.source_module,
            "channel": self.channel,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }