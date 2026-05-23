from __future__ import annotations

from app.core.events import EventBus
from app.knowledge.application.engram_directory import EngramDirectory
from app.knowledge.application.ports import EngramRepositoryPort, KnowledgeRepositoryPort
from app.knowledge.domain import Identity
from app.knowledge.application.ports import KnowledgeRepositoryPort
from app.knowledge.domain import KnowledgeEntry
from app.knowledge.events import (
    CurrentIdentityRequest,
    EngramCreateRequest,
    EngramDeleteRequest,
    EngramHintsRequest,
    EngramListRequest,
    EngramUpdateRequest,
    IdentityResolveRequest,
    KnowledgeItemCreateRequest,
    KnowledgeItemsRequest,
    KnowledgeOverviewRequest,
    PUBLISH_KNOWLEDGE_ENGRAM_CHANGED,
    PUBLISH_KNOWLEDGE_IDENTITY_RESOLVED,
    PUBLISH_KNOWLEDGE_ITEM_CREATED,
    REQUEST_KNOWLEDGE_CURRENT_IDENTITY,
    REQUEST_KNOWLEDGE_ENGRAM_CREATE,
    REQUEST_KNOWLEDGE_ENGRAM_DELETE,
    REQUEST_KNOWLEDGE_ENGRAM_UPDATE,
    REQUEST_KNOWLEDGE_ENGRAMS,
    REQUEST_KNOWLEDGE_IDENTITY_HINTS,
    REQUEST_KNOWLEDGE_IDENTITY_RESOLVE,
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
        self._engrams_loaded = False

    def overview(self, request: KnowledgeOverviewRequest) -> dict[str, object]:
        items = self.list_items(KnowledgeItemsRequest(limit=request.limit))
        titles = [item["title"] for item in items] if request.include_titles else []
        return {
            "item_count": self.repository.count(),
            "recent_items": items,
            "titles": titles,
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