from __future__ import annotations

from app.core.events import EventChannel, EventKind, EventSpec


class WorkshopCreateRequest:
    def __init__(
        self,
        title: str,
        engram_id: str,
        source_documents: list[dict],
        chat_session_id: str | None = None,
    ) -> None:
        self.title = title
        self.engram_id = engram_id
        self.source_documents = source_documents
        self.chat_session_id = chat_session_id


class WorkshopListRequest:
    def __init__(self, limit: int = 20) -> None:
        self.limit = limit


class WorkshopGetRequest:
    def __init__(self, workshop_id: str) -> None:
        self.workshop_id = workshop_id


class WorkshopCloseRequest:
    def __init__(self, workshop_id: str) -> None:
        self.workshop_id = workshop_id


class WorkshopPromoteRequest:
    def __init__(self, workshop_id: str, summary_title: str, summary_text: str) -> None:
        self.workshop_id = workshop_id
        self.summary_title = summary_title
        self.summary_text = summary_text


class WorkshopDeleteRequest:
    def __init__(self, workshop_id: str) -> None:
        self.workshop_id = workshop_id


REQUEST_WORKSHOP_CREATE = EventSpec[WorkshopCreateRequest, dict](
    name="workshop.session.create.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=WorkshopCreateRequest,
    output_type=dict,
)

REQUEST_WORKSHOP_LIST = EventSpec[WorkshopListRequest, list](
    name="workshop.session.list.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=WorkshopListRequest,
    output_type=list,
)

REQUEST_WORKSHOP_GET = EventSpec[WorkshopGetRequest, dict](
    name="workshop.session.get.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=WorkshopGetRequest,
    output_type=dict,
)

REQUEST_WORKSHOP_CLOSE = EventSpec[WorkshopCloseRequest, dict](
    name="workshop.session.close.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=WorkshopCloseRequest,
    output_type=dict,
)

REQUEST_WORKSHOP_PROMOTE = EventSpec[WorkshopPromoteRequest, dict](
    name="workshop.session.promote.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=WorkshopPromoteRequest,
    output_type=dict,
)

REQUEST_WORKSHOP_DELETE = EventSpec[WorkshopDeleteRequest, dict](
    name="workshop.session.delete.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=WorkshopDeleteRequest,
    output_type=dict,
)

__all__ = [
    "WorkshopCreateRequest",
    "WorkshopListRequest",
    "WorkshopGetRequest",
    "WorkshopCloseRequest",
    "WorkshopPromoteRequest",
    "WorkshopDeleteRequest",
    "REQUEST_WORKSHOP_CREATE",
    "REQUEST_WORKSHOP_LIST",
    "REQUEST_WORKSHOP_GET",
    "REQUEST_WORKSHOP_CLOSE",
    "REQUEST_WORKSHOP_PROMOTE",
    "REQUEST_WORKSHOP_DELETE",
]
