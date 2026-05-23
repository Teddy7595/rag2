from __future__ import annotations

from dataclasses import dataclass

from app.knowledge.application.context_pipeline import ContextQueryRouter, ContextRetrieverRuntime, QueryRoutingPlan
from app.knowledge.application.document_ingestion import DocumentIngestionService
from app.knowledge.application.embedding_runtime import SemanticEmbeddingRuntime
from app.knowledge.domain import KnowledgeEntry


@dataclass
class FakeRepository:
    entries: list[KnowledgeEntry]

    def save(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        self.entries.append(entry)
        return entry

    def list_all(self) -> list[KnowledgeEntry]:
        return list(self.entries)

    def list_recent(self, limit: int = 20) -> list[KnowledgeEntry]:
        return list(self.entries)[:limit]

    def count(self) -> int:
        return len(self.entries)


class FakeEmbeddingRuntime(SemanticEmbeddingRuntime):
    def __init__(self) -> None:
        super().__init__(None)
        self.calls: list[str] = []

    def embed_text(self, text: str) -> list[float]:
        self.calls.append(text)
        return [1.0, 0.0]

    def legacy_embed_text(self, text: str) -> list[float]:
        return [1.0, 0.0]


class FakeSemanticIntentRuntime(SemanticEmbeddingRuntime):
    def __init__(self, label: str) -> None:
        super().__init__(None)
        self.label = label
        self.calls: list[str] = []

    def classify_by_prototypes(
        self,
        text: str,
        prototypes: dict[str, tuple[str, ...] | list[str]],
        *,
        threshold: float = 0.24,
        margin: float = 0.03,
    ) -> str | None:
        self.calls.append(text)
        return self.label


def test_document_ingestion_uses_embedding_runtime() -> None:
    runtime = FakeEmbeddingRuntime()
    repository = FakeRepository(entries=[])
    service = DocumentIngestionService(repository=repository, embedding_runtime=runtime)

    payload = service.ingest(
        type(
            "Request",
            (),
            {
                "title": "Documento semantico",
                "tags": (),
                "source_uri": "memory://doc",
                "pdf_path": None,
                "raw_text": "Contexto coherente y relevante.",
                "chunk_size": 50,
                "chunk_overlap": 10,
            },
        )()
    )

    assert runtime.calls
    assert payload["document"]["embedding"] == [1.0, 0.0]
    assert repository.entries[0].embedding == [1.0, 0.0]


def test_context_retrieval_uses_embedding_runtime_for_semantic_match() -> None:
    runtime = FakeEmbeddingRuntime()
    entry = KnowledgeEntry(title="Base", content="sin coincidencia literal", embedding=[1.0, 0.0])
    repository = FakeRepository(entries=[entry])
    retriever = ContextRetrieverRuntime(repository, embedding_runtime=runtime)

    result = retriever.retrieve("pregunta distinta", QueryRoutingPlan(intent="mixed", include_source_types=None, identity_mentions=(), keywords=()))

    assert runtime.calls
    assert result.knowledge_matches
    assert result.knowledge_matches[0].score > 0


def test_context_router_uses_semantic_embeddings_for_route_selection() -> None:
    runtime = FakeSemanticIntentRuntime("identity")
    router = ContextQueryRouter(embedding_runtime=runtime)

    route = router.resolve("el sujeto mantiene su perfil", limit=3)

    assert runtime.calls
    assert route.intent == "identity"
    assert route.include_source_types == ("engrams",)