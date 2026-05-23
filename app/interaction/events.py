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
class InteractionSessionsRequest:
    limit: int = 20


@dataclass(frozen=True)
class InteractionMessageRecordRequest:
    author: str
    content: str
    channel: str = "chat"
    session_id: str | None = None


@dataclass(frozen=True)
class InteractionRealtimeInput:
    content: str
    author: str = "user"
    channel: str = "chat"
    identity_id: str | None = None
    context_limit: int = 5
    history_limit: int = 20
    world_rules: str = ""


@dataclass(frozen=True)
class InteractionSessionRequest:
    session_id: str
    limit: int = 20


@dataclass(frozen=True)
class InteractionSessionConditionsRequest:
    session_id: str
    world_rules: str = ""


@dataclass(frozen=True)
class InteractionMessageActionRequest:
    message_id: str


@dataclass(frozen=True)
class InteractionSessionRewindRequest:
    session_id: str
    message_id: str


@dataclass(frozen=True)
class InteractionContextTraceRequest:
    trace_id: str | None = None
    session_id: str | None = None
    trigger: str | None = None
    limit: int = 100


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

REQUEST_INTERACTION_SESSIONS = EventSpec[InteractionSessionsRequest, list](
    name="interaction.sessions.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=InteractionSessionsRequest,
    output_type=list,
)

REQUEST_INTERACTION_MESSAGE_RECORD = EventSpec[InteractionMessageRecordRequest, dict](
    name="interaction.message.record.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=InteractionMessageRecordRequest,
    output_type=dict,
)

REQUEST_INTERACTION_SESSION_MEMORY = EventSpec[InteractionSessionRequest, dict](
    name="interaction.session.memory.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=InteractionSessionRequest,
    output_type=dict,
)

REQUEST_INTERACTION_SESSION_TOPIC_GRAPH = EventSpec[InteractionSessionRequest, dict](
    name="interaction.session.topic_graph.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=InteractionSessionRequest,
    output_type=dict,
)

REQUEST_INTERACTION_TURN_METRICS = EventSpec[InteractionSessionRequest, list](
    name="interaction.session.turn_metrics.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=InteractionSessionRequest,
    output_type=list,
)

REQUEST_INTERACTION_SESSION_CONDITIONS = EventSpec[InteractionSessionRequest, dict](
    name="interaction.session.conditions.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=InteractionSessionRequest,
    output_type=dict,
)

REQUEST_INTERACTION_SESSION_CONDITIONS_SET = EventSpec[InteractionSessionConditionsRequest, dict](
    name="interaction.session.conditions.set.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=InteractionSessionConditionsRequest,
    output_type=dict,
)

REQUEST_INTERACTION_MESSAGE_HIDE = EventSpec[InteractionMessageActionRequest, dict](
    name="interaction.message.hide.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=InteractionMessageActionRequest,
    output_type=dict,
)

REQUEST_INTERACTION_MESSAGE_MEMORIZE = EventSpec[InteractionMessageActionRequest, dict](
    name="interaction.message.memorize.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=InteractionMessageActionRequest,
    output_type=dict,
)

REQUEST_INTERACTION_SESSION_REWIND = EventSpec[InteractionSessionRewindRequest, dict](
    name="interaction.session.rewind.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=InteractionSessionRewindRequest,
    output_type=dict,
)

REQUEST_INTERACTION_CONTEXT_TRACES = EventSpec[InteractionContextTraceRequest, list](
    name="interaction.context_traces.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=InteractionContextTraceRequest,
    output_type=list,
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
    "InteractionContextTraceRequest",
    "InteractionMessageRecordRequest",
    "InteractionSessionsRequest",
    "InteractionMessageActionRequest",
    "InteractionRealtimeInput",
    "InteractionSessionRewindRequest",
    "InteractionSessionConditionsRequest",
    "InteractionSessionRequest",
    "InteractionSummaryRequest",
    "PUBLISH_INTERACTION_MESSAGE_RECORDED",
    "PUBLISH_INTERACTION_REALTIME_MESSAGE_RECEIVED",
    "PUBLISH_INTERACTION_REALTIME_REPLY_STREAMED",
    "PUBLISH_INTERACTION_REALTIME_SESSION_ENDED",
    "PUBLISH_INTERACTION_REALTIME_SESSION_STARTED",
    "PUBLISH_INTERACTION_REALTIME_TURN_COMPLETED",
    "REQUEST_INTERACTION_CONTEXT_TRACES",
    "REQUEST_INTERACTION_MESSAGE_HIDE",
    "REQUEST_INTERACTION_MESSAGE_MEMORIZE",
    "REQUEST_INTERACTION_MESSAGE_RECORD",
    "REQUEST_INTERACTION_MESSAGES",
    "REQUEST_INTERACTION_SESSIONS",
    "REQUEST_INTERACTION_SESSION_CONDITIONS",
    "REQUEST_INTERACTION_SESSION_CONDITIONS_SET",
    "REQUEST_INTERACTION_SESSION_MEMORY",
    "REQUEST_INTERACTION_SESSION_REWIND",
    "REQUEST_INTERACTION_SESSION_TOPIC_GRAPH",
    "REQUEST_INTERACTION_TURN_METRICS",
    "REQUEST_INTERACTION_SUMMARY",
]