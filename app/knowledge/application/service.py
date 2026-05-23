from __future__ import annotations

from app.core.events import EventBus
from app.knowledge.application.context_pipeline import KnowledgeContextPipeline
from app.knowledge.application.document_ingestion import DocumentIngestionService
from app.knowledge.application.engram_directory import EngramDirectory
from app.knowledge.application.ports import EngramRepositoryPort, KnowledgeRepositoryPort
from app.knowledge.domain import Identity, KnowledgeEntry
from app.knowledge.events import (
    ContextBuildRequest,
    ContextGraphRequest,
    ContextRouteRequest,
    CurrentIdentityRequest,
    DocumentIngestRequest,
    DocumentListRequest,
    DocumentOverviewRequest,
    EngramCreateRequest,
    EngramDeleteRequest,
    EngramHintsRequest,
    EngramListRequest,
    EngramUpdateRequest,
    IdentityResolveRequest,
    KnowledgeItemCreateRequest,
    KnowledgeItemsRequest,
    KnowledgeOverviewRequest,
    PUBLISH_KNOWLEDGE_CONTEXT_PACKED,
    PUBLISH_KNOWLEDGE_CONTEXT_GRAPH_BUILT,
    PUBLISH_KNOWLEDGE_CONTEXT_PROMPT_BUILT,
    PUBLISH_KNOWLEDGE_CONTEXT_ROUTED,
    PUBLISH_KNOWLEDGE_ENGRAM_CHANGED,
    PUBLISH_KNOWLEDGE_DOCUMENT_INGESTED,
    PUBLISH_KNOWLEDGE_IDENTITY_RESOLVED,
    PUBLISH_KNOWLEDGE_ITEM_CREATED,
)


class KnowledgeService:
    def __init__(
        self,
        repository: KnowledgeRepositoryPort,
        event_bus: EventBus,
        engram_repository: EngramRepositoryPort | None = None,
        directory: EngramDirectory | None = None,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.engram_repository = engram_repository
        self.directory = directory or EngramDirectory()
        self.document_ingestion = DocumentIngestionService(repository=self.repository)
        self.context_pipeline = KnowledgeContextPipeline(
            knowledge_repository=self.repository,
            engram_repository=self.engram_repository,
            directory=self.directory,
        )
        self._engrams_loaded = False

    def overview(self, request: KnowledgeOverviewRequest) -> dict[str, object]:
        items = self.list_items(KnowledgeItemsRequest(limit=request.limit))
        titles = [item["title"] for item in items] if request.include_titles else []
        documents = self.document_overview(DocumentOverviewRequest(limit=request.limit))
        return {
            "item_count": self.repository.count(),
            "recent_items": items,
            "titles": titles,
            "document_overview": documents,
        }

    def list_items(self, request: KnowledgeItemsRequest) -> list[dict[str, object]]:
        if request.limit <= 0:
            return []
        items = self.repository.list_recent(limit=request.limit)
        return [item.as_dict() for item in items]

    def create_item(self, request: KnowledgeItemCreateRequest) -> dict[str, object]:
        entry = KnowledgeEntry(title=request.title, content=request.content, tags=list(request.tags))
        saved_entry = self.repository.save(entry)
        payload = saved_entry.as_dict()
        self.event_bus.publish(
            PUBLISH_KNOWLEDGE_ITEM_CREATED,
            payload,
            source_module="knowledge.application.service",
            metadata={"tags": payload["tags"]},
        )
        return payload

    def ingest_document(self, request: DocumentIngestRequest) -> dict[str, object]:
        payload = self.document_ingestion.ingest(request)
        self.event_bus.publish(
            PUBLISH_KNOWLEDGE_DOCUMENT_INGESTED,
            payload,
            source_module="knowledge.application.service",
            metadata={
                "document_id": payload["document"]["document_id"],
                "chunk_count": payload["chunk_count"],
                "page_count": payload["page_count"],
            },
        )
        return payload

    def list_documents(self, request: DocumentListRequest) -> list[dict[str, object]]:
        return self.document_ingestion.list_documents(request)

    def document_overview(self, request: DocumentOverviewRequest) -> dict[str, object]:
        return self.document_ingestion.overview(request)

    def load_engrams(self) -> None:
        self.directory.reset()

        if not self.engram_repository:
            self.directory.ensure_default_identity()
            self._engrams_loaded = True
            return

        identities = self.engram_repository.list_all()
        for identity in identities:
            self.directory.cache(identity)

        if not identities:
            self.directory.ensure_default_identity()

        self._engrams_loaded = True

    def list_engrams(self, request: EngramListRequest) -> list[dict[str, object]]:
        self._ensure_engrams_loaded()
        if request.limit <= 0:
            return []
        engrams = self.directory.list_engrams()[-request.limit :]
        return [identity.as_dict() for identity in engrams]

    def current_identity(self, request: CurrentIdentityRequest) -> dict[str, object]:
        self._ensure_engrams_loaded()
        return self.directory.current_identity().as_dict()

    def resolve_identity(self, request: IdentityResolveRequest) -> dict[str, object]:
        self._ensure_engrams_loaded()
        identity, resolved_text = self.directory.resolve(request.raw_text, request.identity_id)
        payload = {
            "identity": identity.as_dict(),
            "raw_text": request.raw_text,
            "resolved_text": resolved_text,
        }
        self.event_bus.publish(
            PUBLISH_KNOWLEDGE_IDENTITY_RESOLVED,
            payload,
            source_module="knowledge.application.service",
            metadata={"identity_id": identity.id, "identity_name": identity.name},
        )
        return payload

    def list_hint_handles(self, request: EngramHintsRequest) -> list[str]:
        self._ensure_engrams_loaded()
        return self.directory.list_hint_handles()

    def create_engram(self, request: EngramCreateRequest) -> dict[str, object]:
        engram_repository = self._require_engram_repository()
        self._ensure_engrams_loaded()
        identity = Identity(
            name=request.name,
            avatar=request.avatar,
            color_hex=request.color_hex,
            intellectual_profile=request.intellectual_profile,
            behavior_prompt=request.behavior_prompt,
            meta_rule=request.meta_rule,
            moral_threshold=request.moral_threshold,
            interaction_mode=request.interaction_mode,
            dialogue_examples=list(request.dialogue_examples),
            backstory=request.backstory,
            temperatura_base=request.temperatura_base,
            top_p_base=request.top_p_base,
            max_tokens_respuesta=request.max_tokens_respuesta,
        )
        saved_identity = engram_repository.save(identity)
        self.directory.cache(saved_identity)
        payload = saved_identity.as_dict()
        self.event_bus.publish(
            PUBLISH_KNOWLEDGE_ENGRAM_CHANGED,
            {"action": "created", "engram": payload},
            source_module="knowledge.application.service",
            metadata={"action": "created", "engram_id": payload["id"], "name": payload["name"]},
        )
        return payload

    def update_engram(self, request: EngramUpdateRequest) -> dict[str, object]:
        engram_repository = self._require_engram_repository()
        self._ensure_engrams_loaded()
        identity = engram_repository.get_by_id(request.engram_id)
        if not identity:
            return {"updated": False, "engram_id": request.engram_id}

        self._apply_identity_updates(identity, request)
        identity.touch()
        saved_identity = engram_repository.save(identity)
        self.directory.replace(saved_identity)
        payload = saved_identity.as_dict()
        self.event_bus.publish(
            PUBLISH_KNOWLEDGE_ENGRAM_CHANGED,
            {"action": "updated", "engram": payload},
            source_module="knowledge.application.service",
            metadata={"action": "updated", "engram_id": payload["id"], "name": payload["name"]},
        )
        return {"updated": True, "engram": payload}

    def delete_engram(self, request: EngramDeleteRequest) -> dict[str, object]:
        engram_repository = self._require_engram_repository()
        self._ensure_engrams_loaded()
        current = engram_repository.get_by_id(request.engram_id)
        deleted = engram_repository.delete(request.engram_id)
        if deleted:
            self.directory.remove(request.engram_id)
            payload = current.as_dict() if current else {"engram_id": request.engram_id}
            self.event_bus.publish(
                PUBLISH_KNOWLEDGE_ENGRAM_CHANGED,
                {"action": "deleted", "engram": payload},
                source_module="knowledge.application.service",
                metadata={"action": "deleted", "engram_id": request.engram_id},
            )
        return {"deleted": deleted, "engram_id": request.engram_id}

    def route_context(self, request: ContextRouteRequest) -> dict[str, object]:
        route = self.context_pipeline.route_query(request.raw_text, limit=request.limit)
        payload = route.to_dict()
        self.event_bus.publish(
            PUBLISH_KNOWLEDGE_CONTEXT_ROUTED,
            payload,
            source_module="knowledge.application.service",
            metadata={"intent": route.intent, "limit": route.limit},
        )
        return payload

    def build_context_pack(self, request: ContextBuildRequest) -> dict[str, object]:
        preview = self._build_context_preview(request)
        payload = preview.context_pack.to_dict()
        self.event_bus.publish(
            PUBLISH_KNOWLEDGE_CONTEXT_PACKED,
            payload,
            source_module="knowledge.application.service",
            metadata={
                "intent": preview.route.intent,
                "identity_name": preview.identity.name,
                "knowledge_matches": len(preview.context_pack.knowledge_matches),
                "engram_matches": len(preview.context_pack.engram_matches),
            },
        )
        return payload

    def build_prompt(self, request: ContextBuildRequest) -> dict[str, object]:
        preview = self._build_context_preview(request)
        payload = preview.to_dict()
        self.event_bus.publish(
            PUBLISH_KNOWLEDGE_CONTEXT_PROMPT_BUILT,
            payload,
            source_module="knowledge.application.service",
            metadata={"intent": preview.route.intent, "prompt_chars": len(preview.prompt)},
        )
        return payload

    def build_context_graph(self, request: ContextGraphRequest) -> dict[str, object]:
        preview = self._build_context_preview(
            ContextBuildRequest(
                raw_text=request.raw_text,
                limit=request.limit,
                identity_id=request.identity_id,
                history=request.history,
            )
        )

        route = preview.route
        context_pack = preview.context_pack
        identity = preview.identity

        graph_nodes: list[dict[str, object]] = [
            {
                "id": "query",
                "type": "query",
                "label": request.raw_text,
                "metadata": {
                    "intent": route.intent,
                    "keywords": list(route.keywords),
                },
            },
            {
                "id": f"identity:{identity.id}",
                "type": "identity",
                "label": identity.name,
                "metadata": {
                    "hint_handle": identity.hint_handle(),
                },
            },
        ]

        graph_edges: list[dict[str, object]] = [
            {
                "from": "query",
                "to": f"identity:{identity.id}",
                "relation": "resolved_identity",
                "weight": 1.0,
            }
        ]

        for index, match in enumerate(context_pack.knowledge_matches):
            node_id = f"knowledge:{match.source_id}"
            graph_nodes.append(
                {
                    "id": node_id,
                    "type": "knowledge",
                    "label": match.label,
                    "metadata": {
                        "source_type": match.source_type,
                        "excerpt": match.excerpt,
                        "score": match.score,
                    },
                }
            )
            graph_edges.append(
                {
                    "from": "query",
                    "to": node_id,
                    "relation": "retrieved_context",
                    "weight": round(max(0.1, float(match.score) + (0.5 if index == 0 else 0.0)), 3),
                }
            )

        for match in context_pack.engram_matches:
            node_id = f"engram:{match.source_id}"
            graph_nodes.append(
                {
                    "id": node_id,
                    "type": "engram",
                    "label": match.label,
                    "metadata": {
                        "excerpt": match.excerpt,
                        "score": match.score,
                    },
                }
            )
            graph_edges.append(
                {
                    "from": f"identity:{identity.id}",
                    "to": node_id,
                    "relation": "persona_reference",
                    "weight": round(max(0.1, float(match.score)), 3),
                }
            )

        primary_topic = context_pack.knowledge_matches[0].label if context_pack.knowledge_matches else (route.keywords[0] if route.keywords else "")
        secondary_topics = [
            match.label
            for match in context_pack.knowledge_matches[1:4]
            if match.label and match.label != primary_topic
        ]
        if not secondary_topics and len(route.keywords) > 1:
            secondary_topics = [keyword for keyword in route.keywords[1:4] if keyword != primary_topic]

        payload = {
            "intent": route.intent,
            "identity": identity.as_dict(),
            "primary_topic": primary_topic,
            "secondary_topics": secondary_topics,
            "graph": {
                "nodes": graph_nodes,
                "edges": graph_edges,
            },
            "context_pack": context_pack.to_dict(),
        }

        self.event_bus.publish(
            PUBLISH_KNOWLEDGE_CONTEXT_GRAPH_BUILT,
            payload,
            source_module="knowledge.application.service",
            metadata={
                "intent": route.intent,
                "node_count": len(graph_nodes),
                "edge_count": len(graph_edges),
            },
        )
        return payload

    def _build_context_preview(self, request: ContextBuildRequest):
        self._ensure_engrams_loaded()
        return self.context_pipeline.build_preview(
            request.raw_text,
            limit=request.limit,
            identity_id=request.identity_id,
            history=request.history,
        )

    def _ensure_engrams_loaded(self) -> None:
        if not self._engrams_loaded:
            self.load_engrams()

    def _require_engram_repository(self) -> EngramRepositoryPort:
        if not self.engram_repository:
            raise RuntimeError("Engram repository not configured")
        return self.engram_repository

    def _apply_identity_updates(self, identity: Identity, request: EngramUpdateRequest) -> None:
        if request.name is not None:
            identity.name = request.name
        if request.avatar is not None:
            identity.avatar = request.avatar
        if request.color_hex is not None:
            identity.color_hex = request.color_hex
        if request.intellectual_profile is not None:
            identity.intellectual_profile = request.intellectual_profile
        if request.behavior_prompt is not None:
            identity.behavior_prompt = request.behavior_prompt
        if request.meta_rule is not None:
            identity.meta_rule = request.meta_rule
        if request.moral_threshold is not None:
            identity.moral_threshold = request.moral_threshold
        if request.interaction_mode is not None:
            identity.interaction_mode = request.interaction_mode
        if request.dialogue_examples is not None:
            identity.dialogue_examples = list(request.dialogue_examples)
        if request.backstory is not None:
            identity.backstory = request.backstory
        if request.temperatura_base is not None:
            identity.temperatura_base = request.temperatura_base
        if request.top_p_base is not None:
            identity.top_p_base = request.top_p_base
        if request.max_tokens_respuesta is not None:
            identity.max_tokens_respuesta = request.max_tokens_respuesta