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


@dataclass(frozen=True)
class InteractionRealtimeInput:
    content: str
    author: str = "user"
    channel: str = "chat"
    identity_id: str | None = None
    context_limit: int = 5
    history_limit: int = 20


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

PUBLISH_INTERACTION_REALTIME_SESSION_STARTED = EventSpec[dict, dict](
    name="interaction.realtime.session.started",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)

PUBLISH_INTERACTION_REALTIME_MESSAGE_RECEIVED = EventSpec[dict, dict](
    name="interaction.realtime.message.received",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)

PUBLISH_INTERACTION_REALTIME_REPLY_STREAMED = EventSpec[dict, dict](
    name="interaction.realtime.reply.streamed",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)

PUBLISH_INTERACTION_REALTIME_TURN_COMPLETED = EventSpec[dict, dict](
    name="interaction.realtime.turn.completed",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)

PUBLISH_INTERACTION_REALTIME_SESSION_ENDED = EventSpec[dict, dict](
    name="interaction.realtime.session.ended",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)


__all__ = [
    "InteractionHistoryRequest",
    "InteractionMessageRecordRequest",
    "InteractionRealtimeInput",
    "InteractionSummaryRequest",
    "PUBLISH_INTERACTION_MESSAGE_RECORDED",
    "PUBLISH_INTERACTION_REALTIME_MESSAGE_RECEIVED",
    "PUBLISH_INTERACTION_REALTIME_REPLY_STREAMED",
    "PUBLISH_INTERACTION_REALTIME_SESSION_ENDED",
    "PUBLISH_INTERACTION_REALTIME_SESSION_STARTED",
    "PUBLISH_INTERACTION_REALTIME_TURN_COMPLETED",
    "REQUEST_INTERACTION_MESSAGE_RECORD",
    "REQUEST_INTERACTION_MESSAGES",
    "REQUEST_INTERACTION_SUMMARY",
]