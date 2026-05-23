from __future__ import annotations

from dataclasses import dataclass

from app.core.events import EventChannel, EventKind, EventSpec


@dataclass(frozen=True)
class KnowledgeOverviewRequest:
    limit: int = 5
    include_titles: bool = True


@dataclass(frozen=True)
class KnowledgeItemsRequest:
    limit: int = 20


@dataclass(frozen=True)
class KnowledgeItemCreateRequest:
    title: str
    content: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class EngramListRequest:
    limit: int = 20


@dataclass(frozen=True)
class EngramCreateRequest:
    name: str
    avatar: str = ""
    color_hex: str = "#00ff41"
    intellectual_profile: str = "General"
    behavior_prompt: str = ""
    meta_rule: str = "Stay consistent with the selected identity."
    moral_threshold: int = 0
    interaction_mode: str = "Directo"
    dialogue_examples: tuple[str, ...] = ()
    backstory: str = ""
    temperatura_base: float = 0.8
    top_p_base: float = 1.0
    max_tokens_respuesta: int = 2048


@dataclass(frozen=True)
class EngramUpdateRequest:
    engram_id: str
    name: str | None = None
    avatar: str | None = None
    color_hex: str | None = None
    intellectual_profile: str | None = None
    behavior_prompt: str | None = None
    meta_rule: str | None = None
    moral_threshold: int | None = None
    interaction_mode: str | None = None
    dialogue_examples: tuple[str, ...] | None = None
    backstory: str | None = None
    temperatura_base: float | None = None
    top_p_base: float | None = None
    max_tokens_respuesta: int | None = None


@dataclass(frozen=True)
class EngramDeleteRequest:
    engram_id: str


@dataclass(frozen=True)
class EngramImportCsvRequest:
    csv_content: str
    overwrite_existing: bool = True


@dataclass(frozen=True)
class CurrentIdentityRequest:
    pass


@dataclass(frozen=True)
class IdentityResolveRequest:
    raw_text: str
    identity_id: str | None = None


@dataclass(frozen=True)
class EngramHintsRequest:
    pass


@dataclass(frozen=True)
class ContextRouteRequest:
    raw_text: str
    limit: int = 5


@dataclass(frozen=True)
class ContextBuildRequest:
    raw_text: str
    limit: int = 5
    identity_id: str | None = None
    history: str = ""


@dataclass(frozen=True)
class ContextGraphRequest:
    raw_text: str
    limit: int = 7
    identity_id: str | None = None
    history: str = ""


@dataclass(frozen=True)
class DocumentIngestRequest:
    title: str
    raw_text: str | None = None
    pdf_path: str | None = None
    source_uri: str = ""
    tags: tuple[str, ...] = ()
    chunk_size: int = 180
    chunk_overlap: int = 40


@dataclass(frozen=True)
class DocumentListRequest:
    limit: int = 20


@dataclass(frozen=True)
class DocumentOverviewRequest:
    limit: int = 5


REQUEST_KNOWLEDGE_OVERVIEW = EventSpec[KnowledgeOverviewRequest, dict](
    name="knowledge.overview.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=KnowledgeOverviewRequest,
    output_type=dict,
)

REQUEST_KNOWLEDGE_ITEMS = EventSpec[KnowledgeItemsRequest, list](
    name="knowledge.items.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=KnowledgeItemsRequest,
    output_type=list,
)

REQUEST_KNOWLEDGE_ITEM_CREATE = EventSpec[KnowledgeItemCreateRequest, dict](
    name="knowledge.item.create.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=KnowledgeItemCreateRequest,
    output_type=dict,
)

REQUEST_KNOWLEDGE_ENGRAMS = EventSpec[EngramListRequest, list](
    name="knowledge.engrams.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=EngramListRequest,
    output_type=list,
)

REQUEST_KNOWLEDGE_ENGRAM_CREATE = EventSpec[EngramCreateRequest, dict](
    name="knowledge.engram.create.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=EngramCreateRequest,
    output_type=dict,
)

REQUEST_KNOWLEDGE_ENGRAM_UPDATE = EventSpec[EngramUpdateRequest, dict](
    name="knowledge.engram.update.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=EngramUpdateRequest,
    output_type=dict,
)

REQUEST_KNOWLEDGE_ENGRAM_DELETE = EventSpec[EngramDeleteRequest, dict](
    name="knowledge.engram.delete.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=EngramDeleteRequest,
    output_type=dict,
)

REQUEST_KNOWLEDGE_ENGRAM_IMPORT_CSV = EventSpec[EngramImportCsvRequest, dict](
    name="knowledge.engram.import_csv.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=EngramImportCsvRequest,
    output_type=dict,
)

REQUEST_KNOWLEDGE_CURRENT_IDENTITY = EventSpec[CurrentIdentityRequest, dict](
    name="knowledge.identity.current.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=CurrentIdentityRequest,
    output_type=dict,
)

REQUEST_KNOWLEDGE_IDENTITY_RESOLVE = EventSpec[IdentityResolveRequest, dict](
    name="knowledge.identity.resolve.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=IdentityResolveRequest,
    output_type=dict,
)

REQUEST_KNOWLEDGE_IDENTITY_HINTS = EventSpec[EngramHintsRequest, list](
    name="knowledge.identity.hints.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=EngramHintsRequest,
    output_type=list,
)

REQUEST_KNOWLEDGE_CONTEXT_ROUTE = EventSpec[ContextRouteRequest, dict](
    name="knowledge.context.route.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=ContextRouteRequest,
    output_type=dict,
)

REQUEST_KNOWLEDGE_CONTEXT_PACK = EventSpec[ContextBuildRequest, dict](
    name="knowledge.context.pack.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=ContextBuildRequest,
    output_type=dict,
)

REQUEST_KNOWLEDGE_CONTEXT_PROMPT = EventSpec[ContextBuildRequest, dict](
    name="knowledge.context.prompt.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=ContextBuildRequest,
    output_type=dict,
)

REQUEST_KNOWLEDGE_CONTEXT_GRAPH = EventSpec[ContextGraphRequest, dict](
    name="knowledge.context.graph.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=ContextGraphRequest,
    output_type=dict,
)

REQUEST_KNOWLEDGE_DOCUMENT_INGEST = EventSpec[DocumentIngestRequest, dict](
    name="knowledge.document.ingest.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=DocumentIngestRequest,
    output_type=dict,
)

REQUEST_KNOWLEDGE_DOCUMENTS = EventSpec[DocumentListRequest, list](
    name="knowledge.documents.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=DocumentListRequest,
    output_type=list,
)

REQUEST_KNOWLEDGE_DOCUMENT_OVERVIEW = EventSpec[DocumentOverviewRequest, dict](
    name="knowledge.documents.overview.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=DocumentOverviewRequest,
    output_type=dict,
)

PUBLISH_KNOWLEDGE_ITEM_CREATED = EventSpec[dict, dict](
    name="knowledge.item.created",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)

PUBLISH_KNOWLEDGE_ENGRAM_CHANGED = EventSpec[dict, dict](
    name="knowledge.engram.changed",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)

PUBLISH_KNOWLEDGE_IDENTITY_RESOLVED = EventSpec[dict, dict](
    name="knowledge.identity.resolved",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)

PUBLISH_KNOWLEDGE_CONTEXT_ROUTED = EventSpec[dict, dict](
    name="knowledge.context.routed",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)

PUBLISH_KNOWLEDGE_CONTEXT_PACKED = EventSpec[dict, dict](
    name="knowledge.context.packed",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)

PUBLISH_KNOWLEDGE_CONTEXT_PROMPT_BUILT = EventSpec[dict, dict](
    name="knowledge.context.prompt.built",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)

PUBLISH_KNOWLEDGE_CONTEXT_GRAPH_BUILT = EventSpec[dict, dict](
    name="knowledge.context.graph.built",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)

PUBLISH_KNOWLEDGE_DOCUMENT_INGESTED = EventSpec[dict, dict](
    name="knowledge.document.ingested",
    kind=EventKind.PUBLISH,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)


__all__ = [
    "KnowledgeItemCreateRequest",
    "KnowledgeItemsRequest",
    "KnowledgeOverviewRequest",
    "CurrentIdentityRequest",
    "ContextBuildRequest",
    "ContextGraphRequest",
    "ContextRouteRequest",
    "DocumentIngestRequest",
    "DocumentListRequest",
    "DocumentOverviewRequest",
    "EngramCreateRequest",
    "EngramDeleteRequest",
    "EngramHintsRequest",
    "EngramListRequest",
    "EngramUpdateRequest",
    "IdentityResolveRequest",
    "PUBLISH_KNOWLEDGE_ITEM_CREATED",
    "PUBLISH_KNOWLEDGE_ENGRAM_CHANGED",
    "PUBLISH_KNOWLEDGE_CONTEXT_PACKED",
    "PUBLISH_KNOWLEDGE_CONTEXT_GRAPH_BUILT",
    "PUBLISH_KNOWLEDGE_CONTEXT_PROMPT_BUILT",
    "PUBLISH_KNOWLEDGE_CONTEXT_ROUTED",
    "PUBLISH_KNOWLEDGE_IDENTITY_RESOLVED",
    "PUBLISH_KNOWLEDGE_DOCUMENT_INGESTED",
    "REQUEST_KNOWLEDGE_CURRENT_IDENTITY",
    "REQUEST_KNOWLEDGE_CONTEXT_GRAPH",
    "REQUEST_KNOWLEDGE_CONTEXT_PACK",
    "REQUEST_KNOWLEDGE_CONTEXT_PROMPT",
    "REQUEST_KNOWLEDGE_CONTEXT_ROUTE",
    "REQUEST_KNOWLEDGE_DOCUMENT_INGEST",
    "REQUEST_KNOWLEDGE_DOCUMENT_OVERVIEW",
    "REQUEST_KNOWLEDGE_DOCUMENTS",
    "REQUEST_KNOWLEDGE_ENGRAM_CREATE",
    "REQUEST_KNOWLEDGE_ENGRAM_DELETE",
    "REQUEST_KNOWLEDGE_ENGRAM_UPDATE",
    "REQUEST_KNOWLEDGE_ENGRAMS",
    "REQUEST_KNOWLEDGE_IDENTITY_HINTS",
    "REQUEST_KNOWLEDGE_IDENTITY_RESOLVE",
    "REQUEST_KNOWLEDGE_ITEM_CREATE",
    "REQUEST_KNOWLEDGE_ITEMS",
    "REQUEST_KNOWLEDGE_OVERVIEW",
]