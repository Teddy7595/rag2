from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.bootstrap import create_app


def build_simple_pdf_bytes(text: str) -> bytes:
    def escape_pdf_text(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", r"\(").replace(")", r"\)")

    content_stream = f"BT /F1 18 Tf 72 720 Td ({escape_pdf_text(text)}) Tj ET\n".encode("utf-8")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        b"5 0 obj\n<< /Length %d >>\nstream\n%s\nendstream\nendobj\n" % (len(content_stream), content_stream),
    ]

    output = [b"%PDF-1.4\n"]
    offsets = [0]
    current_offset = len(output[0])
    for obj in objects:
        offsets.append(current_offset)
        output.append(obj)
        current_offset += len(obj)

    xref_offset = current_offset
    xref_lines = [b"xref\n0 6\n0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref_lines.append(f"{offset:010d} 00000 n \n".encode("ascii"))

    trailer = b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + str(xref_offset).encode("ascii") + b"\n%%EOF\n"
    return b"".join(output) + b"".join(xref_lines) + trailer


def build_test_app(tmp_path: Path, monkeypatch) -> object:
    vault_dir = tmp_path / "vault"
    ai_model_dir = tmp_path / "ai_model"
    database_path = tmp_path / "rag2.sqlite3"

    monkeypatch.setenv("VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("AI_MODEL_DIR", str(ai_model_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{database_path}")
    monkeypatch.setenv("DATABASE_CREATE_SCHEMA_ON_START", "true")
    monkeypatch.setenv("DATABASE_ECHO", "false")

    return create_app()


def test_bootstrap_exposes_database_and_module_routes(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)

    assert app.state.context.database is not None
    assert app.state.context.database.settings.is_sqlite

    route_paths = {route.path for route in app.routes if hasattr(route, "path")}
    expected_paths = {
        "/api/platform/health",
        "/api/interaction/messages",
        "/api/interaction/summary",
        "/api/knowledge/items",
        "/api/knowledge/context/pack",
        "/api/knowledge/context/prompt",
        "/api/knowledge/context/route",
        "/api/knowledge/documents",
        "/api/knowledge/documents/overview",
        "/api/knowledge/documents/ingest",
        "/api/knowledge/engrams",
        "/api/knowledge/engrams/{engram_id}",
        "/api/knowledge/overview",
        "/api/knowledge/identity/current",
        "/api/knowledge/identity/hints",
        "/api/knowledge/identity/resolve",
        "/api/operations/audit-log",
        "/api/operations/status",
    }
    assert expected_paths <= route_paths


def test_modules_work_through_event_bus_and_persist(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        health_response = client.get("/api/platform/health")
        assert health_response.status_code == 200
        assert health_response.json()["status"] == "ok"

        knowledge_response = client.post(
            "/api/knowledge/items",
            json={
                "title": "Primer conocimiento",
                "content": "Contenido base",
                "tags": ["seed"],
            },
        )
        assert knowledge_response.status_code == 200
        assert knowledge_response.json()["title"] == "Primer conocimiento"

        message_response = client.post(
            "/api/interaction/messages",
            json={"author": "user", "content": "Hola", "channel": "chat"},
        )
        assert message_response.status_code == 200

        summary_response = client.get("/api/interaction/summary", params={"limit": 5})
        assert summary_response.status_code == 200
        summary_payload = summary_response.json()
        assert summary_payload["message_count"] == 1
        assert summary_payload["channel_counts"]["chat"] == 1
        assert summary_payload["knowledge_overview"]["item_count"] == 1

        engram_response = client.post(
            "/api/knowledge/engrams",
            json={
                "name": "Atlas",
                "behavior_prompt": "Responde con claridad y foco.",
                "dialogue_examples": ["Hola Atlas"],
            },
        )
        assert engram_response.status_code == 200
        engram_payload = engram_response.json()
        assert engram_payload["name"] == "Atlas"

        update_response = client.patch(
            f"/api/knowledge/engrams/{engram_payload['id']}",
            json={"backstory": "Base de identidad persistente"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["backstory"] == "Base de identidad persistente"

        resolve_response = client.post(
            "/api/knowledge/identity/resolve",
            json={"raw_text": "Hola @Atlas, genera un resumen.", "identity_id": None},
        )
        assert resolve_response.status_code == 200
        resolve_payload = resolve_response.json()
        assert resolve_payload["identity"]["name"] == "Atlas"
        assert "@Atlas" not in resolve_payload["resolved_text"]

        route_response = client.get(
            "/api/knowledge/context/route",
            params={"raw_text": "@Atlas resume el conocimiento base", "limit": 5},
        )
        assert route_response.status_code == 200
        route_payload = route_response.json()
        assert route_payload["intent"] == "mixed"
        assert route_payload["include_source_types"] is None
        assert "Atlas" in route_payload["identity_mentions"]

        pack_response = client.post(
            "/api/knowledge/context/pack",
            json={
                "raw_text": "@Atlas resume el conocimiento base",
                "limit": 5,
                "identity_id": None,
                "history": "user: revisa el contexto",
            },
        )
        assert pack_response.status_code == 200
        pack_payload = pack_response.json()
        assert pack_payload["identity"]["name"] == "Atlas"
        assert "Primer conocimiento" in pack_payload["context_text"]
        assert "Atlas" in pack_payload["context_text"]

        prompt_response = client.post(
            "/api/knowledge/context/prompt",
            json={
                "raw_text": "@Atlas resume el conocimiento base",
                "limit": 5,
                "identity_id": None,
                "history": "user: revisa el contexto",
            },
        )
        assert prompt_response.status_code == 200
        prompt_payload = prompt_response.json()
        assert prompt_payload["identity"]["name"] == "Atlas"
        assert "Primer conocimiento" in prompt_payload["prompt"]
        assert "Atlas" in prompt_payload["prompt"]

        pdf_path = tmp_path / "documento_base.pdf"
        pdf_text = (
            "Atlas documento base para la fase cuatro. "
            "Este texto define el indice de memoria y el chunking del sistema. "
            "Cada chunk debe conservar el contexto, la pagina y la fuente."
        )
        pdf_path.write_bytes(build_simple_pdf_bytes(pdf_text))

        document_ingest_response = client.post(
            "/api/knowledge/documents/ingest",
            json={
                "title": "Documento base",
                "pdf_path": str(pdf_path),
                "source_uri": "vault://documento_base.pdf",
                "tags": ["phase4", "pdf"],
                "chunk_size": 8,
                "chunk_overlap": 2,
            },
        )
        assert document_ingest_response.status_code == 200
        document_payload = document_ingest_response.json()
        assert document_payload["page_count"] == 1
        assert document_payload["chunk_count"] >= 2
        assert document_payload["document"]["source_type"] == "document"

        documents_overview_response = client.get("/api/knowledge/documents/overview", params={"limit": 5})
        assert documents_overview_response.status_code == 200
        documents_overview = documents_overview_response.json()
        assert documents_overview["document_count"] == 1
        assert documents_overview["chunk_count"] >= 2

        documents_list_response = client.get("/api/knowledge/documents", params={"limit": 5})
        assert documents_list_response.status_code == 200
        assert any(item["title"] == "Documento base" for item in documents_list_response.json())

        document_context_response = client.post(
            "/api/knowledge/context/pack",
            json={
                "raw_text": "@Atlas resume el documento base y el indice de memoria",
                "limit": 10,
                "identity_id": None,
                "history": "user: analiza el pdf",
            },
        )
        assert document_context_response.status_code == 200
        document_context_payload = document_context_response.json()
        assert "Documento base" in document_context_payload["context_text"]
        assert "chunking del sistema" in document_context_payload["context_text"]
        assert any(
            match["source_type"] in {"document", "document_chunk"}
            for match in document_context_payload["knowledge_matches"]
        )

        document_prompt_response = client.post(
            "/api/knowledge/context/prompt",
            json={
                "raw_text": "@Atlas resume el documento base y el indice de memoria",
                "limit": 10,
                "identity_id": None,
                "history": "user: analiza el pdf",
            },
        )
        assert document_prompt_response.status_code == 200
        document_prompt_payload = document_prompt_response.json()
        assert "Documento base" in document_prompt_payload["prompt"]

        current_identity_response = client.get("/api/knowledge/identity/current")
        assert current_identity_response.status_code == 200
        assert current_identity_response.json()["name"] == "Atlas"

        hints_response = client.get("/api/knowledge/identity/hints")
        assert hints_response.status_code == 200
        assert "@Atlas" in hints_response.json()

        status_response = client.get("/api/operations/status", params={"limit": 10})
        assert status_response.status_code == 200
        status_payload = status_response.json()
        assert status_payload["captured_events"] >= 10
        assert status_payload["event_counts"]["knowledge.item.created"] >= 1
        assert status_payload["event_counts"]["interaction.message.recorded"] >= 1
        assert status_payload["event_counts"]["knowledge.engram.changed"] >= 2
        assert status_payload["event_counts"]["knowledge.identity.resolved"] >= 1
        assert status_payload["event_counts"]["knowledge.context.routed"] >= 1
        assert status_payload["event_counts"]["knowledge.context.packed"] >= 1
        assert status_payload["event_counts"]["knowledge.context.prompt.built"] >= 1
        assert status_payload["event_counts"]["knowledge.document.ingested"] >= 1

    app_again = build_test_app(tmp_path, monkeypatch)

    with TestClient(app_again) as client_again:
        knowledge_items_response = client_again.get("/api/knowledge/items", params={"limit": 10})
        assert knowledge_items_response.status_code == 200
        assert any(item["title"] == "Primer conocimiento" for item in knowledge_items_response.json())

        documents_again = client_again.get("/api/knowledge/documents", params={"limit": 10})
        assert documents_again.status_code == 200
        assert any(item["title"] == "Documento base" for item in documents_again.json())

        documents_overview_again = client_again.get("/api/knowledge/documents/overview", params={"limit": 10})
        assert documents_overview_again.status_code == 200
        assert documents_overview_again.json()["document_count"] == 1

        engrams_response = client_again.get("/api/knowledge/engrams", params={"limit": 10})
        assert engrams_response.status_code == 200
        assert any(item["name"] == "Atlas" for item in engrams_response.json())

        route_again = client_again.get(
            "/api/knowledge/context/route",
            params={"raw_text": "@Atlas resume el conocimiento base", "limit": 5},
        )
        assert route_again.status_code == 200

        prompt_again = client_again.post(
            "/api/knowledge/context/prompt",
            json={
                "raw_text": "@Atlas resume el documento base y el indice de memoria",
                "limit": 10,
                "identity_id": None,
                "history": "user: revisa el pdf",
            },
        )
        assert prompt_again.status_code == 200
        prompt_again_payload = prompt_again.json()
        assert "Documento base" in prompt_again_payload["prompt"]
        assert "chunking del sistema" in prompt_again_payload["prompt"]

        current_identity_again = client_again.get("/api/knowledge/identity/current")
        assert current_identity_again.status_code == 200
        assert current_identity_again.json()["name"] == "Atlas"

        hints_again = client_again.get("/api/knowledge/identity/hints")
        assert hints_again.status_code == 200
        assert "@Atlas" in hints_again.json()

        interaction_messages_response = client_again.get("/api/interaction/messages", params={"limit": 10})
        assert interaction_messages_response.status_code == 200
        assert any(message["content"] == "Hola" for message in interaction_messages_response.json())

        interaction_summary_response = client_again.get("/api/interaction/summary", params={"limit": 10})
        assert interaction_summary_response.status_code == 200
        assert interaction_summary_response.json()["message_count"] == 1

        audit_log_response = client_again.get("/api/operations/audit-log", params={"limit": 100})
        assert audit_log_response.status_code == 200
        audit_log_payload = audit_log_response.json()
        assert any(entry["event_name"] == "knowledge.item.created" for entry in audit_log_payload)
        assert any(entry["event_name"] == "knowledge.document.ingested" for entry in audit_log_payload)