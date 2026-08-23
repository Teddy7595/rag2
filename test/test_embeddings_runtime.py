from __future__ import annotations

from dataclasses import dataclass

from app.knowledge.application.context_pipeline import ContextQueryRouter, ContextRetrieverRuntime, QueryRoutingPlan
from app.knowledge.application.document_ingestion import DocumentIngestionService
from app.knowledge.application.embedding_runtime import OllamaEmbeddingRuntime, SemanticEmbeddingRuntime
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


def test_context_router_mention_with_topic_still_searches_knowledge() -> None:
    """Regression: @mención (elegir engrama) no debe apagar la búsqueda de
    conocimiento cuando el mensaje también trae una pregunta de contenido real —
    causa raíz confirmada de un bug reportado en producción (sesión real donde
    "Hola @Mistress Keynes, ... cultura Kemet ..." devolvía knowledge_count=0)."""
    router = ContextQueryRouter()

    route = router.resolve(
        "Hola @Mistress Keynes, me contaron que eres experta en la cultura Kemet "
        "y sus historias de su cultura social enfocadas a la fornicación y el sexo "
        "desenfrenado como religión y como vida de hogar",
        limit=5,
    )

    assert route.intent != "identity"
    assert route.include_source_types is None or "knowledge_entries" in route.include_source_types
    assert route.identity_mentions == ("Mistress",)


def test_ollama_embedding_runtime_calls_api_embed_and_parses_response(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    def fake_post(url: str, json: dict, timeout: float) -> FakeResponse:
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse({"embeddings": [[0.1, 0.2, 0.3]]})

    monkeypatch.setattr("httpx.post", fake_post)

    runtime = OllamaEmbeddingRuntime("http://localhost:11434", "nomic-embed-text")
    result = runtime.embed_text("hola mundo")

    assert result == [0.1, 0.2, 0.3]
    assert calls == [
        {
            "url": "http://localhost:11434/api/embed",
            "json": {"model": "nomic-embed-text", "input": "hola mundo"},
            "timeout": 30.0,
        }
    ]


def test_ollama_embedding_runtime_falls_back_to_hash_on_http_error(monkeypatch) -> None:
    def fake_post(*args: object, **kwargs: object) -> None:
        raise RuntimeError("connection refused")

    monkeypatch.setattr("httpx.post", fake_post)

    runtime = OllamaEmbeddingRuntime("http://localhost:11434", "nomic-embed-text")

    assert runtime.embed_text("hola mundo") == runtime.legacy_embed_text("hola mundo")


def test_context_router_pure_identity_question_still_routes_to_identity() -> None:
    router = ContextQueryRouter()

    route = router.resolve("Cual es tu rol?", limit=5)

    assert route.intent == "identity"
    assert route.include_source_types == ("engrams",)