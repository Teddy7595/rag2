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


def build_test_app(tmp_path: Path, monkeypatch, extra_env: dict[str, str] | None = None) -> object:
    vault_dir = tmp_path / "vault"
    ai_model_dir = tmp_path / "ai_models"
    database_path = tmp_path / "rag2.sqlite3"

    monkeypatch.setenv("VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("AI_MODEL_DIR", str(ai_model_dir))
    monkeypatch.setenv("AI_MODELS_DIR", str(ai_model_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{database_path}")
    monkeypatch.setenv("DATABASE_CREATE_SCHEMA_ON_START", "true")
    monkeypatch.setenv("DATABASE_ECHO", "false")

    for key, value in (extra_env or {}).items():
        monkeypatch.setenv(key, value)

    return create_app()


def test_bootstrap_exposes_database_and_module_routes(tmp_path: Path, monkeypatch, capsys) -> None:
    app = build_test_app(tmp_path, monkeypatch)
    captured = capsys.readouterr()

    assert app.state.context.database is not None
    assert app.state.context.database.settings.is_sqlite
    assert "Registered routes:" in captured.out
    assert "/api/platform/health" in captured.out

    route_paths = {route.path for route in app.routes if hasattr(route, "path")}
    expected_paths = {
        "/",
        "/admin",
        "/admin/routes",
        "/admin/models",
        "/api/platform/health",
        "/api/interaction/messages",
        "/api/interaction/summary",
        "/api/interaction/stream",
        "/api/operations/sagas",
        "/api/operations/sagas/{saga_id}",
        "/api/operations/sagas/{saga_id}/commands",
        "/api/storage/overview",
        "/api/storage/public",
        "/api/storage/uploads",
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
        "/api/models/catalog",
        "/api/models/selection",
        "/public",
        "/uploads",
        "/ws/chat",
    }
    assert expected_paths <= route_paths


def test_modules_work_through_event_bus_and_persist(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        landing_response = client.get("/")
        assert landing_response.status_code == 200
        assert "Centro de control" in landing_response.text

        admin_response = client.get("/admin")
        assert admin_response.status_code == 200
        assert "Panel de administración" in admin_response.text

        models_response = client.get("/admin/models")
        assert models_response.status_code == 200
        assert "Modelos y proveedores" in models_response.text

        frontend_response = client.get("/ui-assets/")
        assert frontend_response.status_code == 200
        assert "RAG2 Control Plane" in frontend_response.text

        routes_response = client.get("/admin/routes")
        assert routes_response.status_code == 200
        assert "Visualizador de rutas" in routes_response.text
        assert "/api/operations/sagas" in routes_response.text

        storage_overview_response = client.get("/api/storage/overview")
        assert storage_overview_response.status_code == 200
        storage_overview = storage_overview_response.json()
        assert storage_overview["public_file_count"] == 0
        assert storage_overview["upload_file_count"] == 0

        storage_service = app.state.context.services["storage"]
        public_file = storage_service.public_dir / "hola-publico.txt"
        upload_file = storage_service.uploads_dir / "hola-upload.txt"
        public_file.write_text("publico", encoding="utf-8")
        upload_file.write_text("privado", encoding="utf-8")

        public_asset_response = client.get("/public/hola-publico.txt")
        assert public_asset_response.status_code == 200
        assert public_asset_response.text == "publico"

        upload_asset_response = client.get("/uploads/hola-upload.txt")
        assert upload_asset_response.status_code == 200
        assert upload_asset_response.text == "privado"

        refreshed_storage_response = client.get("/api/storage/overview")
        assert refreshed_storage_response.status_code == 200
        refreshed_storage = refreshed_storage_response.json()
        assert refreshed_storage["public_file_count"] == 1
        assert refreshed_storage["upload_file_count"] == 1

        model_bundle_dir = app.state.context.settings.ai_model_dir / "Gemma-4-E4B-Uncensored-HauhauCS-Aggressive"
        model_bundle_dir.mkdir(parents=True, exist_ok=True)
        text_model_path = model_bundle_dir / "Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-Q8_K_P.gguf"
        projector_path = model_bundle_dir / "mmproj-Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-f16.gguf"
        text_model_path.write_bytes(b"text-model")
        projector_path.write_bytes(b"vision-model")

        catalog_response = client.get("/api/models/catalog")
        assert catalog_response.status_code == 200
        catalog_payload = catalog_response.json()
        assert catalog_payload["summary"]["bundle_count"] >= 1
        bundle_payload = next(bundle for bundle in catalog_payload["bundles"] if bundle["bundle_id"] == "Gemma-4-E4B-Uncensored-HauhauCS-Aggressive")
        assert bundle_payload["supports_text"] is True
        assert bundle_payload["supports_vision"] is True

        selection_response = client.patch(
            "/api/models/selection",
            json={"text_provider": "local", "text_bundle_id": "Gemma-4-E4B-Uncensored-HauhauCS-Aggressive"},
        )
        assert selection_response.status_code == 200
        assert selection_response.json()["selection"]["text_bundle_id"] == "Gemma-4-E4B-Uncensored-HauhauCS-Aggressive"

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
        assert status_payload["saga_count"] == 0
        assert status_payload["event_counts"]["knowledge.item.created"] >= 1
        assert status_payload["event_counts"]["interaction.message.recorded"] >= 1
        assert status_payload["event_counts"]["knowledge.engram.changed"] >= 2
        assert status_payload["event_counts"]["knowledge.identity.resolved"] >= 1
        assert status_payload["event_counts"]["knowledge.context.routed"] >= 1
        assert status_payload["event_counts"]["knowledge.context.packed"] >= 1
        assert status_payload["event_counts"]["knowledge.context.prompt.built"] >= 1
        assert status_payload["event_counts"]["knowledge.document.ingested"] >= 1

        saga_start_response = client.post(
            "/api/operations/sagas",
            json={
                "title": "Saga Atlas",
                "premise": "Explorar la memoria persistente del sistema.",
                "summary": "Flujo narrativo de comandos.",
                "world_building": "Un monolito modular que recuerda cada acto.",
                "initial_command": "abre el acto inicial",
            },
        )
        assert saga_start_response.status_code == 200
        saga_payload = saga_start_response.json()
        assert saga_payload["title"] == "Saga Atlas"
        assert saga_payload["command_count"] == 1
        assert saga_payload["act_count"] == 1

        saga_append_response = client.post(
            f"/api/operations/sagas/{saga_payload['id']}/commands",
            json={"command": "avanza al siguiente acto", "note": "cierre del primer giro"},
        )
        assert saga_append_response.status_code == 200
        saga_append_payload = saga_append_response.json()
        assert saga_append_payload["appended"] is True
        assert saga_append_payload["saga"]["command_count"] == 2

        saga_detail_response = client.get(f"/api/operations/sagas/{saga_payload['id']}")
        assert saga_detail_response.status_code == 200
        saga_detail = saga_detail_response.json()
        assert saga_detail["title"] == "Saga Atlas"
        assert saga_detail["command_count"] == 2
        assert saga_detail["last_command"] == "avanza al siguiente acto"

        saga_update_response = client.patch(
            f"/api/operations/sagas/{saga_payload['id']}",
            json={
                "title": "Saga Atlas Renacida",
                "status": "paused",
                "world_building": "Un monolito modular que aprende de cada acto.",
            },
        )
        assert saga_update_response.status_code == 200
        saga_update_payload = saga_update_response.json()
        assert saga_update_payload["updated"] is True
        assert saga_update_payload["saga"]["title"] == "Saga Atlas Renacida"
        assert saga_update_payload["saga"]["status"] == "paused"

        temp_saga_response = client.post(
            "/api/operations/sagas",
            json={
                "title": "Saga Temporal",
                "premise": "Una historia efimera para probar delete.",
                "initial_command": "abre un acto que desaparece",
            },
        )
        assert temp_saga_response.status_code == 200
        temp_saga_id = temp_saga_response.json()["id"]

        saga_delete_response = client.delete(f"/api/operations/sagas/{temp_saga_id}")
        assert saga_delete_response.status_code == 200
        saga_delete_payload = saga_delete_response.json()
        assert saga_delete_payload["deleted"] is True

        sagas_list_response = client.get("/api/operations/sagas", params={"limit": 10})
        assert sagas_list_response.status_code == 200
        sagas_list_payload = sagas_list_response.json()
        assert any(item["title"] == "Saga Atlas Renacida" for item in sagas_list_payload)
        assert all(item["title"] != "Saga Temporal" for item in sagas_list_payload)

        status_after_saga_response = client.get("/api/operations/status", params={"limit": 10})
        assert status_after_saga_response.status_code == 200
        status_after_saga = status_after_saga_response.json()
        assert status_after_saga["saga_count"] >= 1
        assert status_after_saga["event_counts"]["operations.saga.started"] >= 1
        assert status_after_saga["event_counts"]["operations.saga.command.appended"] >= 1
        assert status_after_saga["event_counts"]["operations.saga.updated"] >= 1
        assert status_after_saga["event_counts"]["operations.saga.deleted"] >= 1

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

        sagas_again = client_again.get("/api/operations/sagas", params={"limit": 10})
        assert sagas_again.status_code == 200
        assert any(item["title"] == "Saga Atlas Renacida" for item in sagas_again.json())
        assert all(item["title"] != "Saga Temporal" for item in sagas_again.json())

        saga_detail_again = client_again.get(f"/api/operations/sagas/{saga_payload['id']}")
        assert saga_detail_again.status_code == 200
        saga_detail_again_payload = saga_detail_again.json()
        assert saga_detail_again_payload["title"] == "Saga Atlas Renacida"
        assert saga_detail_again_payload["command_count"] == 2

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
        assert any(entry["event_name"] == "operations.saga.started" for entry in audit_log_payload)
        assert any(entry["event_name"] == "operations.saga.command.appended" for entry in audit_log_payload)
        assert any(entry["event_name"] == "operations.saga.updated" for entry in audit_log_payload)
        assert any(entry["event_name"] == "operations.saga.deleted" for entry in audit_log_payload)


def test_security_middleware_applies_rate_limit_and_ban_list(tmp_path: Path, monkeypatch) -> None:
    limited_app = build_test_app(
        tmp_path / "limited",
        monkeypatch,
        extra_env={"APP_RATE_LIMIT_MAX_REQUESTS": "2", "APP_RATE_LIMIT_WINDOW_SECONDS": "60"},
    )

    with TestClient(limited_app) as client:
        first_response = client.get("/api/platform/health")
        second_response = client.get("/api/platform/health")
        third_response = client.get("/api/platform/health")

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        assert third_response.status_code == 429
        assert third_response.json()["detail"] == "Rate limit exceeded"

    banned_app = build_test_app(
        tmp_path / "banned",
        monkeypatch,
        extra_env={"APP_BAN_LIST": "testclient"},
    )

    with TestClient(banned_app) as client:
        banned_response = client.get("/api/platform/health")
        assert banned_response.status_code == 403
        assert banned_response.json()["detail"] == "Client is banned"


def test_realtime_gateway_streams_turns_and_persists(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        knowledge_response = client.post(
            "/api/knowledge/items",
            json={
                "title": "Base de conocimiento realtime",
                "content": "Atlas responde con contexto persistente y trazable.",
                "tags": ["realtime", "chat"],
            },
        )
        assert knowledge_response.status_code == 200

        engram_response = client.post(
            "/api/knowledge/engrams",
            json={
                "name": "Atlas",
                "behavior_prompt": "Responde con claridad y foco.",
                "dialogue_examples": ["Hola Atlas"],
            },
        )
        assert engram_response.status_code == 200

        with client.websocket_connect("/ws/chat") as websocket:
            bootstrap_types: list[str] = []
            for _ in range(8):
                packet = websocket.receive_json()
                bootstrap_types.append(str(packet["type"]))
                if packet["type"] == "welcome":
                    break

            assert "session_started" in bootstrap_types
            assert "meta_update" in bootstrap_types
            assert "welcome" in bootstrap_types

            websocket.send_json(
                {
                    "content": "Atlas resume la base de conocimiento realtime",
                    "context_limit": 5,
                    "history_limit": 5,
                }
            )

            turn_types: list[str] = []
            assistant_message_text = ""
            while True:
                packet = websocket.receive_json()
                turn_types.append(str(packet["type"]))
                if packet["type"] == "assistant_message":
                    assistant_message_text = str(packet["message"]["content"])
                if packet["type"] == "turn_complete":
                    break

            assert "turn_started" in turn_types
            assert "assistant_message" in turn_types
            assert "Contexto recuperado" in assistant_message_text
            assert "Base de conocimiento realtime" in assistant_message_text

        sse_response = client.post(
            "/api/interaction/stream",
            json={
                "content": "Atlas vuelve a resumir la base de conocimiento realtime",
                "context_limit": 5,
                "history_limit": 5,
            },
        )
        assert sse_response.status_code == 200
        sse_text = sse_response.text
        assert "event: session_started" in sse_text
        assert "event: turn_complete" in sse_text
        assert "assistant_message" in sse_text

        status_response = client.get("/api/operations/status", params={"limit": 200})
        assert status_response.status_code == 200
        status_payload = status_response.json()
        assert status_payload["event_counts"]["interaction.realtime.session.started"] >= 2
        assert status_payload["event_counts"]["interaction.realtime.message.received"] >= 2
        assert status_payload["event_counts"]["interaction.realtime.reply.streamed"] >= 2
        assert status_payload["event_counts"]["interaction.realtime.turn.completed"] >= 2

    app_again = build_test_app(tmp_path, monkeypatch)

    with TestClient(app_again) as client_again:
        messages_response = client_again.get("/api/interaction/messages", params={"limit": 50})
        assert messages_response.status_code == 200
        messages = messages_response.json()
        assert any(message["channel"] == "assistant" for message in messages)
        assert any(
            "Base de conocimiento realtime" in message["content"]
            for message in messages
            if message["channel"] == "assistant"
        )

        summary_response = client_again.get("/api/interaction/summary", params={"limit": 50})
        assert summary_response.status_code == 200
        summary_payload = summary_response.json()
        assert summary_payload["channel_counts"]["assistant"] >= 2