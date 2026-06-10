from __future__ import annotations

import base64
import csv
import io
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from app.core.events import EventBus
from app.knowledge.application.embedding_runtime import SemanticEmbeddingRuntime
from app.knowledge.application.context_pipeline import KnowledgeContextPipeline
from app.knowledge.application.document_ingestion import (
    DocumentIngestionService,
    _clean_ingested_text,
    _read_pdf_image_metadata,
)
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
    EngramImportCsvRequest,
    EngramHintsRequest,
    EngramListRequest,
    EngramMemoryStatsRequest,
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
from app.models.events import ModelVisionAnalysisRequest, REQUEST_MODEL_VISION_ANALYSIS


class KnowledgeService:
    _ENGRAM_IMPORT_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
        "id": ("id", "engram_id", "identity_id"),
        "name": ("name", "nombre", "engrama", "identidad", "character", "persona"),
        "avatar": ("avatar", "avatar_url", "image", "imagen", "foto", "photo"),
        "color_hex": ("color_hex", "color", "hex", "accent_color", "color_principal"),
        "intellectual_profile": (
            "intellectual_profile",
            "profile",
            "perfil",
            "arquetipo",
            "archetype",
        ),
        "behavior_prompt": (
            "behavior_prompt",
            "prompt",
            "system_prompt",
            "base_prompt",
            "rol_prompt",
        ),
        "meta_rule": (
            "meta_rule",
            "meta_rules",
            "rule",
            "rules",
            "regla",
            "reglas",
            "room_rules",
        ),
        "dialogue_examples": (
            "dialogue_examples",
            "examples",
            "example_dialogue",
            "dialogos",
            "ejemplos",
        ),
        "backstory": ("backstory", "historia", "trasfondo", "bio", "contexto"),
    }

    def __init__(
        self,
        repository: KnowledgeRepositoryPort,
        event_bus: EventBus,
        engram_repository: EngramRepositoryPort | None = None,
        directory: EngramDirectory | None = None,
        embedding_model_dir: Path | None = None,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.engram_repository = engram_repository
        self.directory = directory or EngramDirectory()
        self.embedding_runtime = SemanticEmbeddingRuntime(embedding_model_dir)
        self.document_ingestion = DocumentIngestionService(repository=self.repository, embedding_runtime=self.embedding_runtime)
        self.context_pipeline = KnowledgeContextPipeline(
            knowledge_repository=self.repository,
            engram_repository=self.engram_repository,
            directory=self.directory,
            embedding_runtime=self.embedding_runtime,
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
        payload["vision_enrichment"] = self._enrich_pdf_images_with_vision(payload, request)
        self.event_bus.publish(
            PUBLISH_KNOWLEDGE_DOCUMENT_INGESTED,
            payload,
            source_module="knowledge.application.service",
            metadata={
                "document_id": payload["document"]["document_id"],
                "chunk_count": payload["chunk_count"],
                "page_count": payload["page_count"],
                "vision_count": len(payload.get("vision_enrichment", []) or []),
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
        if not identities:
            seeded_identity = self.engram_repository.save(self._build_base_assistant_identity())
            identities = [seeded_identity]

        for identity in identities:
            self.directory.cache(identity)

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

    def engram_memory_stats(self, request: EngramMemoryStatsRequest) -> dict[str, object]:
        engram_id = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(request.engram_id or "").strip()).strip("-._")
        if not engram_id:
            return {
                "engram_id": "",
                "tag": "",
                "total_memories": 0,
                "by_source_type": {},
                "document_count": 0,
            }

        target_tag = f"engram:{engram_id}".lower()
        by_source_type: dict[str, int] = {}
        document_ids: set[str] = set()
        total = 0

        for entry in self.repository.list_all():
            tags = [str(tag or "").strip().lower() for tag in list(entry.tags or [])]
            if target_tag not in tags:
                continue
            source_type = str(entry.source_type or "manual")
            by_source_type[source_type] = int(by_source_type.get(source_type, 0)) + 1
            if str(entry.document_id or "").strip():
                document_ids.add(str(entry.document_id).strip())
            total += 1

        return {
            "engram_id": engram_id,
            "tag": target_tag,
            "total_memories": total,
            "by_source_type": dict(sorted(by_source_type.items(), key=lambda item: item[0])),
            "document_count": len(document_ids),
        }

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
            dialogue_examples=list(request.dialogue_examples),
            backstory=request.backstory,
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

    def import_engrams_csv(self, request: EngramImportCsvRequest) -> dict[str, object]:
        engram_repository = self._require_engram_repository()
        self._ensure_engrams_loaded()

        raw_csv = (request.csv_content or "").strip()
        if not raw_csv:
            return {
                "imported": 0,
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "errors": ["CSV vacio."],
                "mapped_columns": {},
            }

        reader = csv.DictReader(io.StringIO(raw_csv))
        if not reader.fieldnames:
            return {
                "imported": 0,
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "errors": ["CSV sin encabezados."],
                "mapped_columns": {},
            }

        mapped_columns = self._resolve_import_column_map(reader.fieldnames)
        existing_identities = engram_repository.list_all()
        by_id = {identity.id: identity for identity in existing_identities}
        by_name = {self._normalize_identity_name(identity.name): identity for identity in existing_identities if identity.name.strip()}

        created = 0
        updated = 0
        skipped = 0
        errors: list[str] = []

        for row_index, row in enumerate(reader, start=2):
            mapped = self._map_import_row(row, mapped_columns)
            name = mapped.get("name", "").strip()
            if not name:
                skipped += 1
                errors.append(f"Fila {row_index}: nombre vacio, se omite.")
                continue

            target_identity: Identity | None = None
            provided_id = mapped.get("id", "").strip()
            if provided_id:
                target_identity = by_id.get(provided_id)

            if target_identity is None:
                target_identity = by_name.get(self._normalize_identity_name(name))

            if target_identity is None:
                created_identity = Identity(name=name)
                self._apply_import_payload(created_identity, mapped)
                saved_identity = engram_repository.save(created_identity)
                self.directory.cache(saved_identity)
                by_id[saved_identity.id] = saved_identity
                by_name[self._normalize_identity_name(saved_identity.name)] = saved_identity
                created += 1
                self.event_bus.publish(
                    PUBLISH_KNOWLEDGE_ENGRAM_CHANGED,
                    {"action": "created", "engram": saved_identity.as_dict()},
                    source_module="knowledge.application.service",
                    metadata={"action": "created", "engram_id": saved_identity.id, "name": saved_identity.name},
                )
                continue

            if not request.overwrite_existing:
                skipped += 1
                continue

            self._apply_import_payload(target_identity, mapped)
            target_identity.touch()
            saved_identity = engram_repository.save(target_identity)
            self.directory.replace(saved_identity)
            by_id[saved_identity.id] = saved_identity
            by_name[self._normalize_identity_name(saved_identity.name)] = saved_identity
            updated += 1
            self.event_bus.publish(
                PUBLISH_KNOWLEDGE_ENGRAM_CHANGED,
                {"action": "updated", "engram": saved_identity.as_dict()},
                source_module="knowledge.application.service",
                metadata={"action": "updated", "engram_id": saved_identity.id, "name": saved_identity.name},
            )

        return {
            "imported": created + updated,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "mapped_columns": mapped_columns,
        }

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
            source_filter=request.source_filter,
        )

    def _ensure_engrams_loaded(self) -> None:
        if not self._engrams_loaded:
            self.load_engrams()

    def _require_engram_repository(self) -> EngramRepositoryPort:
        if not self.engram_repository:
            raise RuntimeError("Engram repository not configured")
        return self.engram_repository

    def _build_base_assistant_identity(self) -> Identity:
        return Identity(
            name="Asistente Base",
            avatar="",
            color_hex="#00ff41",
            intellectual_profile="Asistente operativo para RAG y tareas tecnicas",
            behavior_prompt=(
                "Responde en espanol claro, directo y accionable. Prioriza exactitud, "
                "pasos concretos y contexto util para ejecutar tareas reales."
            ),
            meta_rule=(
                "- Mantener coherencia con el contexto recuperado.\n"
                "- Si falta informacion, explicitar supuestos breves.\n"
                "- No inventar hechos externos al contexto."
            ),
            dialogue_examples=[
                "Te doy un resumen operativo y luego los pasos exactos.",
                "Confirmo estado actual y riesgos antes de proponer cambios.",
            ],
            backstory="Identidad base del sistema para inicializar nuevas sesiones.",
        )

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
        if request.dialogue_examples is not None:
            identity.dialogue_examples = list(request.dialogue_examples)
        if request.backstory is not None:
            identity.backstory = request.backstory

    def _resolve_import_column_map(self, fieldnames: list[str]) -> dict[str, str]:
        normalized_headers = {self._normalize_import_column(name): name for name in fieldnames}
        mapping: dict[str, str] = {}
        for target_field, aliases in self._ENGRAM_IMPORT_FIELD_ALIASES.items():
            for alias in aliases:
                resolved = normalized_headers.get(self._normalize_import_column(alias))
                if resolved:
                    mapping[target_field] = resolved
                    break
        return mapping

    def _map_import_row(self, row: dict[str, str | None], mapping: dict[str, str]) -> dict[str, str]:
        payload: dict[str, str] = {}
        for target_field, source_column in mapping.items():
            raw_value = row.get(source_column)
            payload[target_field] = str(raw_value or "").strip()
        return payload

    @staticmethod
    def _normalize_import_column(value: str) -> str:
        lowered = value.strip().lower()
        lowered = re.sub(r"\s+", "_", lowered)
        lowered = re.sub(r"[^a-z0-9_]+", "", lowered)
        return lowered

    @staticmethod
    def _normalize_identity_name(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    def _apply_import_payload(self, identity: Identity, payload: dict[str, str]) -> None:
        if payload.get("name"):
            identity.name = payload["name"]
        if payload.get("avatar"):
            identity.avatar = payload["avatar"]
        if payload.get("color_hex"):
            identity.color_hex = payload["color_hex"]
        if payload.get("intellectual_profile"):
            identity.intellectual_profile = payload["intellectual_profile"]
        if payload.get("behavior_prompt"):
            identity.behavior_prompt = payload["behavior_prompt"]
        if payload.get("meta_rule"):
            identity.meta_rule = self._normalize_meta_rule(payload["meta_rule"])
        if payload.get("backstory"):
            identity.backstory = payload["backstory"]

        dialogue_examples = self._parse_dialogue_examples(payload.get("dialogue_examples", ""))
        if dialogue_examples:
            identity.dialogue_examples = dialogue_examples

    @staticmethod
    def _normalize_meta_rule(raw: str) -> str:
        text = raw.strip()
        if not text:
            return text
        parts = [item.strip() for item in re.split(r"\r?\n|;|\|", text) if item.strip()]
        if len(parts) <= 1:
            return text
        return "\n".join(f"- {item.lstrip('-* ').strip()}" for item in parts)

    @staticmethod
    def _parse_dialogue_examples(raw: str) -> list[str]:
        if not raw.strip():
            return []
        parts = [item.strip() for item in re.split(r"\r?\n|;|\|", raw) if item.strip()]
        unique: list[str] = []
        for item in parts:
            if item not in unique:
                unique.append(item)
        return unique

    @staticmethod
    def _parse_int(raw: str, *, minimum: int, maximum: int) -> int | None:
        text = raw.strip()
        if not text:
            return None
        try:
            value = int(float(text))
        except ValueError:
            return None
        return max(minimum, min(maximum, value))

    @staticmethod
    def _parse_float(raw: str, *, minimum: float, maximum: float) -> float | None:
        text = raw.strip().replace(",", ".")
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
        return max(minimum, min(maximum, value))

    def _enrich_pdf_images_with_vision(
        self,
        payload: dict[str, object],
        request: DocumentIngestRequest,
    ) -> list[dict[str, object]]:
        source_uri = str(request.source_uri or request.pdf_path or "")
        if not source_uri.lower().endswith(".pdf"):
            return []

        if not request.pdf_path:
            return []
        try:
            artifacts = _read_pdf_image_metadata(request.pdf_path)
        except Exception:
            return []
        if not artifacts:
            return []

        document = payload.get("document") if isinstance(payload.get("document"), dict) else {}
        document_id = str((document or {}).get("document_id") or "")
        document_title = str((document or {}).get("title") or request.title)

        enriched_rows: list[dict[str, object]] = []
        with TemporaryDirectory(prefix="rag2_pdf_images_") as temp_dir:
            for image in artifacts:
                encoded = str(image.get("data_base64") or "").strip()
                if not encoded:
                    continue

                try:
                    image_bytes = base64.b64decode(encoded)
                except Exception:
                    continue

                extension = str(image.get("extension") or "png").strip(".") or "png"
                page_number = int(image.get("page_number") or 0)
                image_index = int(image.get("image_index") or 0)
                file_name = f"p{page_number:03d}_img{image_index:03d}.{extension}"
                file_path = Path(temp_dir) / file_name
                file_path.write_bytes(image_bytes)

                analysis = self.event_bus.request(
                    REQUEST_MODEL_VISION_ANALYSIS,
                    ModelVisionAnalysisRequest(
                        image_path=str(file_path),
                        prompt="Extrae texto visible y describe elementos narrativos relevantes para RAG.",
                        max_tokens=256,
                    ),
                    source_module="knowledge.application.service",
                )
                if not isinstance(analysis, dict):
                    continue

                summary = str(analysis.get("content") or analysis.get("result") or "").strip()
                if not summary:
                    continue

                cleaned_summary = _clean_ingested_text(summary)
                if not cleaned_summary:
                    continue

                vision_entry = KnowledgeEntry(
                    title=f"{document_title} :: vision p{page_number} #{image_index}",
                    content=cleaned_summary,
                    tags=["document", "image", "vision", f"page:{page_number}"],
                    source_type="document_image_vision",
                    source_uri=source_uri,
                    document_id=document_id,
                    document_title=document_title,
                    page_number=page_number,
                    chunk_index=image_index,
                    chunk_count=None,
                    source_chars=len(cleaned_summary),
                    embedding=self.embedding_runtime.embed_text(cleaned_summary),
                )
                saved = self.repository.save(vision_entry)
                row = saved.as_dict()
                row["analysis_preview"] = cleaned_summary[:280]
                enriched_rows.append(row)

        return enriched_rows