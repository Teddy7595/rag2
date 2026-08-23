from __future__ import annotations

from pathlib import Path

from app.knowledge.application.document_ingestion import _chunk_words
from app.knowledge.events import DocumentDeleteRequest, DocumentIngestRequest, DocumentTagsUpdateRequest, EngramCreateRequest
from test.test_integration import build_test_app


def test_chunk_words_never_splits_mid_sentence() -> None:
    text = (
        "Primera oracion breve. Segunda oracion con un poco mas de contenido para probar el empaquetado. "
        "Tercera oracion, bastante mas larga, que agrega varias clausulas adicionales para forzar un corte "
        "de chunk en algun punto intermedio del parrafo de prueba. Cuarta y ultima oracion del texto."
    )
    chunks = _chunk_words(text, chunk_size=25, overlap=5)

    assert chunks
    for chunk in chunks:
        assert chunk.strip()
        assert chunk.rstrip()[-1] in ".!?", f"chunk no termina en limite de oracion: {chunk!r}"


def test_chunk_words_handles_oversized_single_sentence() -> None:
    long_sentence = "palabra " * 250 + "fin."
    chunks = _chunk_words(long_sentence, chunk_size=180, overlap=40)

    assert len(chunks) >= 2
    assert all(chunk.strip() for chunk in chunks)


def test_chunk_words_uses_injected_token_counter_instead_of_word_count() -> None:
    # "Xx" always counts as 3 tokens, every other word as 1 — a unit
    # deliberately different from a plain word count, to prove `_chunk_words`
    # sizes/packs sentences against whatever `count_tokens` reports instead of
    # `len(sentence.split())`.
    def count_tokens(text: str) -> int:
        return sum(3 if word.lower() == "xx" else 1 for word in text.split())

    text = "Uno dos tres. Xx dos tres cuatro."

    # By word count both sentences (3 + 4 = 7 words) fit in one chunk_size=8 chunk.
    chunks_by_words = _chunk_words(text, chunk_size=8, overlap=0)
    assert chunks_by_words == ["Uno dos tres. Xx dos tres cuatro."]

    # By token count the second sentence alone is 3+1+1+1=6 tokens; combined
    # with the first sentence's 3 tokens that's 9 > chunk_size=8, forcing a
    # split the word-count version never makes.
    chunks_by_tokens = _chunk_words(text, chunk_size=8, overlap=0, count_tokens=count_tokens)
    assert chunks_by_tokens == ["Uno dos tres.", "Xx dos tres cuatro."]


def test_list_by_document_id_returns_all_chunks_ordered(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)
    knowledge_service = app.state.context.services["knowledge"]

    text = " ".join(
        f"Esta es la oracion numero {i} del documento de prueba con contenido variado." for i in range(20)
    )
    result = knowledge_service.ingest_document(
        DocumentIngestRequest(title="Doc de prueba", raw_text=text, chunk_size=25, chunk_overlap=5)
    )
    document_id = str(result["document"]["document_id"])

    siblings = knowledge_service.repository.list_by_document_id(document_id)
    chunk_siblings = [entry for entry in siblings if entry.source_type == "document_chunk"]

    assert len(chunk_siblings) == len(result["chunks"])
    assert len(chunk_siblings) > 1
    indices = [entry.chunk_index for entry in chunk_siblings]
    assert indices == sorted(indices)


def test_retrieve_includes_parent_document_match_for_top_chunk(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)
    knowledge_service = app.state.context.services["knowledge"]

    text = (
        "El protocolo de emergencia establece que el operador debe verificar la presion antes de continuar. "
        "Una vez verificada la presion, se procede a cerrar la valvula principal del sistema hidraulico. "
        "El siguiente paso consiste en registrar la lectura final en la bitacora de mantenimiento. "
        "Finalmente se notifica al supervisor de turno sobre el cierre exitoso del procedimiento."
    )
    knowledge_service.ingest_document(
        DocumentIngestRequest(title="Manual de operacion", raw_text=text, chunk_size=15, chunk_overlap=3)
    )

    preview = knowledge_service.context_pipeline.build_preview("valvula principal del sistema hidraulico", limit=3)
    matches = preview.context_pack.knowledge_matches

    parent_matches = [match for match in matches if match.source_type == "document_parent"]
    assert len(parent_matches) == 1

    parent = parent_matches[0]
    assert "protocolo de emergencia" in parent.excerpt.lower()
    assert "notifica al supervisor" in parent.excerpt.lower()

    top_chunk_matches = [match for match in matches if match.source_type == "document_chunk"]
    assert top_chunk_matches, "deberia haber al menos un match de chunk ademas del parent"
    assert len(parent.excerpt) > len(top_chunk_matches[0].excerpt)


def test_retrieve_expands_parent_matches_for_multiple_top_documents(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)
    knowledge_service = app.state.context.services["knowledge"]

    doc_a_text = (
        "El manual hidraulico describe la valvula principal del sistema hidraulico industrial. "
        "El operador debe verificar la presion de la valvula principal antes de cada turno. "
        "Un cierre incorrecto de la valvula principal puede danar el sistema hidraulico completo. "
        "Se recomienda inspeccionar la valvula principal del sistema hidraulico semanalmente."
    )
    doc_b_text = (
        "El protocolo electrico cubre el tablero principal del sistema hidraulico secundario. "
        "El tecnico debe desenergizar el tablero principal antes de intervenir el sistema hidraulico. "
        "Cada intervencion sobre el sistema hidraulico secundario se registra en la bitacora electrica. "
        "El tablero principal del sistema hidraulico secundario requiere revision mensual obligatoria."
    )
    knowledge_service.ingest_document(
        DocumentIngestRequest(title="Manual hidraulico A", raw_text=doc_a_text, chunk_size=15, chunk_overlap=3)
    )
    knowledge_service.ingest_document(
        DocumentIngestRequest(title="Manual hidraulico B", raw_text=doc_b_text, chunk_size=15, chunk_overlap=3)
    )

    preview = knowledge_service.context_pipeline.build_preview("valvula principal del sistema hidraulico", limit=6)
    matches = preview.context_pack.knowledge_matches

    parent_matches = [match for match in matches if match.source_type == "document_parent"]
    assert len(parent_matches) == 2

    document_ids = {match.metadata["document_id"] for match in parent_matches}
    assert len(document_ids) == 2, "cada expansion debe corresponder a un documento distinto, sin duplicados"


def test_build_preview_skips_retrieval_for_raw_mode_engram(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)
    knowledge_service = app.state.context.services["knowledge"]

    knowledge_service.ingest_document(
        DocumentIngestRequest(
            title="Manual tecnico",
            raw_text="La valvula principal del sistema hidraulico requiere mantenimiento periodico.",
            chunk_size=15,
            chunk_overlap=3,
        )
    )
    engram = knowledge_service.create_engram(
        EngramCreateRequest(
            name="Ajustador Tecnico",
            behavior_prompt="Sos un asistente tecnico para afinar prompts de otros engramas.",
            meta_rule="No inventes datos.",
            raw_mode=True,
        )
    )

    preview = knowledge_service.context_pipeline.build_preview(
        "valvula principal del sistema hidraulico", identity_id=engram["id"], limit=3
    )

    assert preview.context_pack.knowledge_matches == ()
    assert preview.identity.behavior_prompt == "Sos un asistente tecnico para afinar prompts de otros engramas."
    assert preview.identity.meta_rule == "No inventes datos."


def test_build_preview_still_retrieves_for_non_raw_mode_engram(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)
    knowledge_service = app.state.context.services["knowledge"]

    knowledge_service.ingest_document(
        DocumentIngestRequest(
            title="Manual tecnico",
            raw_text="La valvula principal del sistema hidraulico requiere mantenimiento periodico.",
            chunk_size=15,
            chunk_overlap=3,
        )
    )
    engram = knowledge_service.create_engram(
        EngramCreateRequest(name="Asistente Normal", behavior_prompt="Responde con normalidad.")
    )

    preview = knowledge_service.context_pipeline.build_preview(
        "valvula principal del sistema hidraulico", identity_id=engram["id"], limit=3
    )

    assert preview.context_pack.knowledge_matches != ()


def test_delete_document_removes_all_entries_for_that_document(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)
    knowledge_service = app.state.context.services["knowledge"]

    text = " ".join(f"Oracion numero {i} del documento a borrar con contenido variado." for i in range(20))
    result = knowledge_service.ingest_document(
        DocumentIngestRequest(title="Doc a borrar", raw_text=text, chunk_size=25, chunk_overlap=5)
    )
    document_id = str(result["document"]["document_id"])
    assert knowledge_service.repository.list_by_document_id(document_id) != []

    delete_result = knowledge_service.delete_document(DocumentDeleteRequest(document_id=document_id))
    assert delete_result["ok"] is True
    assert delete_result["deleted_entries"] > 0
    assert knowledge_service.repository.list_by_document_id(document_id) == []


def test_delete_document_returns_not_ok_for_unknown_document(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)
    knowledge_service = app.state.context.services["knowledge"]

    delete_result = knowledge_service.delete_document(DocumentDeleteRequest(document_id="does-not-exist"))
    assert delete_result["ok"] is False
    assert delete_result["deleted_entries"] == 0


def test_update_document_tags_replaces_tags_on_every_entry(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)
    knowledge_service = app.state.context.services["knowledge"]

    text = " ".join(f"Oracion numero {i} del documento a etiquetar con contenido variado." for i in range(20))
    result = knowledge_service.ingest_document(
        DocumentIngestRequest(title="Doc a etiquetar", raw_text=text, chunk_size=25, chunk_overlap=5, tags=("vieja",))
    )
    document_id = str(result["document"]["document_id"])

    update_result = knowledge_service.update_document_tags(
        DocumentTagsUpdateRequest(document_id=document_id, tags=("nueva", "revisado"))
    )
    assert update_result["ok"] is True
    assert update_result["updated_entries"] > 0

    entries = knowledge_service.repository.list_by_document_id(document_id)
    assert entries
    for entry in entries:
        assert entry.tags == ["nueva", "revisado"]
