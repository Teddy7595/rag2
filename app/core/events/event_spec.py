from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar


InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class EventKind(str, Enum):
    REQUEST = "request"
    PUBLISH = "publish"


class EventChannel(str, Enum):
    DOMAIN = "domain"
    AUDIT = "audit"
    INTEGRATION = "integration"
    NOTIFICATION = "notification"


@dataclass(frozen=True)
class EventSpec(Generic[InputT, OutputT]):
    name: str
    kind: EventKind
    channel: EventChannel
    input_type: type[InputT] | None = None
    output_type: type[OutputT] | None = None