from __future__ import annotations

from dataclasses import dataclass

from app.core.events import EventChannel, EventKind, EventSpec


@dataclass(frozen=True)
class InteractionSummaryRequest:
    limit: int = 5


@dataclass(frozen=True)
class InteractionHistoryRequest:
    limit: int = 20


@dataclass(frozen=True)
class InteractionMessageRecordRequest:
    author: str
    content: str
    channel: str = "chat"


REQUEST_INTERACTION_SUMMARY = EventSpec[InteractionSummaryRequest, dict](
    name="interaction.summary.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=InteractionSummaryRequest,
    output_type=dict,
)

REQUEST_INTERACTION_MESSAGES = EventSpec[InteractionHistoryRequest, list](
    name="interaction.messages.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=InteractionHistoryRequest,
    output_type=list,
)

REQUEST_INTERACTION_MESSAGE_RECORD = EventSpec[InteractionMessageRecordRequest, dict](
    name="interaction.message.record.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=InteractionMessageRecordRequest,
    output_type=dict,
)

PUBLISH_INTERACTION_MESSAGE_RECORDED = EventSpec[dict, dict](
    name="interaction.message.recorded",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)


__all__ = [
    "InteractionHistoryRequest",
    "InteractionMessageRecordRequest",
    "InteractionSummaryRequest",
    "PUBLISH_INTERACTION_MESSAGE_RECORDED",
    "REQUEST_INTERACTION_MESSAGE_RECORD",
    "REQUEST_INTERACTION_MESSAGES",
    "REQUEST_INTERACTION_SUMMARY",
]