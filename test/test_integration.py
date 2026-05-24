from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.core.settings import load_settings


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


def test_settings_prefers_ai_models_when_configured_ai_model_is_empty(tmp_path: Path, monkeypatch) -> None:
    ai_models_dir = tmp_path / "ai_models"
    ai_models_dir.mkdir(parents=True, exist_ok=True)
    (ai_models_dir / "Phi-plain-root.gguf").write_bytes(b"model")

    # Simulate stale local env that points to ai_model while actual artifacts live in ai_models.
    (tmp_path / "ai_model").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AI_MODEL_DIR", "./ai_model")
    monkeypatch.delenv("AI_MODELS_DIR", raising=False)

    settings = load_settings(tmp_path)
    assert settings.ai_model_dir == ai_models_dir.resolve()


def test_settings_loads_conversation_rollout_flags(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONVERSATION_GUARD_ENABLED", "false")
    monkeypatch.setenv("APP_CONVERSATION_SANITIZE_ENABLED", "true")
    monkeypatch.setenv("APP_CONVERSATION_TIMEOUT_ENABLED", "false")
    monkeypatch.setenv("APP_CONVERSATION_TELEMETRY_ENABLED", "false")
    monkeypatch.setenv("APP_CONVERSATION_DEBUG_TRACE_ENABLED", "true")
    monkeypatch.setenv("APP_CONVERSATION_DEADLINE_SCALE_PERCENT", "175")
    monkeypatch.setenv("APP_CONVERSATION_INTENT_BUNDLE_ID", "intent-small")
    monkeypatch.setenv("APP_CONVERSATION_INTENT_MAX_TOKENS", "6")

    settings = load_settings(tmp_path)
    assert settings.conversation_guard_enabled is False
    assert settings.conversation_sanitize_enabled is True
    assert settings.conversation_timeout_enabled is False
    assert settings.conversation_telemetry_enabled is False
    assert settings.conversation_debug_trace_enabled is True
    assert settings.conversation_deadline_scale_percent == 175
    assert settings.conversation_intent_bundle_id == "intent-small"
    assert settings.conversation_intent_max_tokens == 6


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
        "/admin/runtime-ai",
        "/admin/context-graph",
        "/admin/sagas",
        "/admin/session-intel",
        "/admin/context-traces",
        "/admin/engrams",
        "/chat",
        "/admin/routes",
        "/admin/models",
        "/api/platform/health",
        "/api/interaction/messages",
        "/api/interaction/messages/{message_id}",
        "/api/interaction/messages/{message_id}/memorize",
        "/api/interaction/summary",
        "/api/interaction/sessions",
        "/api/interaction/sessions/deleted",
        "/api/interaction/sessions/{session_id}",
        "/api/interaction/sessions/{session_id}/restore",
        "/api/interaction/stream",
        "/api/interaction/sessions/{session_id}/rewind/{message_id}",
        "/api/interaction/sessions/{session_id}/memory",
        "/api/interaction/sessions/{session_id}/messages",
        "/api/interaction/sessions/{session_id}/topics",
        "/api/interaction/sessions/{session_id}/metrics",
        "/api/interaction/sessions/{session_id}/conditions",
        "/api/admin/context-traces",
        "/api/operations/sagas",
        "/api/operations/sagas/{saga_id}",
        "/api/operations/sagas/{saga_id}/commands",
        "/api/operations/sagas/{saga_id}/consistency",
        "/api/operations/sagas/{saga_id}/debate",
        "/api/operations/sagas/{saga_id}/next-context",
        "/api/operations/sagas/{saga_id}/retcon",
        "/api/storage/overview",
        "/api/storage/public",
        "/api/storage/uploads",
        "/api/storage/vault/files",
        "/api/storage/chats/{session_id}/assets",
        "/api/storage/engrams/avatar",
        "/api/storage/vault/ingest",
        "/api/knowledge/items",
        "/api/knowledge/context/pack",
        "/api/knowledge/context/prompt",
        "/api/knowledge/context/graph",
        "/api/knowledge/context/route",
        "/api/knowledge/documents",
        "/api/knowledge/documents/overview",
        "/api/knowledge/documents/ingest",
        "/api/knowledge/engrams",
        "/api/knowledge/engrams/{engram_id}",
        "/api/knowledge/engrams/import/csv",
        "/api/knowledge/overview",
        "/api/knowledge/identity/current",
        "/api/knowledge/identity/hints",
        "/api/knowledge/identity/resolve",
        "/api/operations/audit-log",
        "/api/operations/status",
        "/api/models/catalog",
        "/api/models/selection",
        "/api/models/runtime-config",
        "/api/models/apply-restart-stream",
        "/api/models/runtime/status",
        "/api/models/runtime/text",
        "/api/models/runtime/vision",
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
        assert "/admin/engrams" in admin_response.text
        assert "/admin/context-graph" in admin_response.text
        assert "/admin/sagas" in admin_response.text

        chat_response = client.get("/chat")
        assert chat_response.status_code == 200
        assert "Chat realtime" in chat_response.text
        assert "/admin/session-intel" in chat_response.text

        models_response = client.get("/admin/models")
        assert models_response.status_code == 200
        assert "Modelos y proveedores" in models_response.text

        runtime_admin_response = client.get("/admin/runtime-ai")
        assert runtime_admin_response.status_code == 200
        assert "Modelos y proveedores" in runtime_admin_response.text

        context_graph_admin_response = client.get("/admin/context-graph")
        assert context_graph_admin_response.status_code == 200
        assert "Laboratorio de coherencia" in context_graph_admin_response.text

        sagas_admin_response = client.get("/admin/sagas")
        assert sagas_admin_response.status_code == 200
        assert "Sala de continuidad narrativa" in sagas_admin_response.text
        assert "/api/operations/sagas" in sagas_admin_response.text

        session_intel_admin_response = client.get("/admin/session-intel")
        assert session_intel_admin_response.status_code == 200
        assert "Monitor de continuidad por sesion" in session_intel_admin_response.text
        assert "rag2.activeRealtimeSessionId" in session_intel_admin_response.text

        context_traces_admin_response = client.get("/admin/context-traces")
        assert context_traces_admin_response.status_code == 200
        assert "Inspector de trazas de contexto" in context_traces_admin_response.text

        engrams_admin_response = client.get("/admin/engrams")
        assert engrams_admin_response.status_code == 200
        assert "Gestor de engramas" in engrams_admin_response.text

        base_hints_response = client.get("/api/knowledge/identity/hints")
        assert base_hints_response.status_code == 200
        assert "@Asistente Base" in base_hints_response.json()

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

        vault_files_response = client.get("/api/storage/vault/files", params={"limit": 100})
        assert vault_files_response.status_code == 200
        assert any(item["relative_path"].endswith("public/hola-publico.txt") for item in vault_files_response.json())

        chat_asset_upload = client.post(
            "/api/storage/chats/test-room/assets",
            files={"file": ("nota.txt", b"contenido de sala", "text/plain")},
        )
        assert chat_asset_upload.status_code == 200
        chat_asset_payload = chat_asset_upload.json()
        assert chat_asset_payload["file_name"] == "nota.txt"
        assert "uploads/chats/test-room/nota.txt" in chat_asset_payload["relative_path"]

        chat_asset_list = client.get("/api/storage/chats/test-room/assets")
        assert chat_asset_list.status_code == 200
        assert "nota.txt" in chat_asset_list.json()

        avatar_upload = client.post(
            "/api/storage/engrams/avatar",
            files={"file": ("atlas.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        )
        assert avatar_upload.status_code == 200
        assert avatar_upload.json()["public_url"].startswith("/uploads/engrams/")

        model_bundle_dir = app.state.context.settings.ai_model_dir / "Gemma-4-E4B-Uncensored-HauhauCS-Aggressive"
        model_bundle_dir.mkdir(parents=True, exist_ok=True)
        text_model_path = model_bundle_dir / "Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-Q8_K_P.gguf"
        projector_path = model_bundle_dir / "mmproj-Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-f16.gguf"
        text_model_path.write_bytes(b"text-model")
        projector_path.write_bytes(b"vision-model")

        flat_model_path = app.state.context.settings.ai_model_dir / "Phi-plain-root.gguf"
        flat_model_path.write_bytes(b"flat-root-model")

        catalog_response = client.get("/api/models/catalog")
        assert catalog_response.status_code == 200
        catalog_payload = catalog_response.json()
        assert catalog_payload["summary"]["bundle_count"] >= 1
        assert catalog_payload["runtime"]["runtime_adapter_status"] == "wired"
        assert catalog_payload["runtime"]["flat_file_support"] is True
        assert catalog_payload["validation"]["invalid_bundle_count"] >= 1
        bundle_payload = next(bundle for bundle in catalog_payload["bundles"] if bundle["bundle_id"] == "Gemma-4-E4B-Uncensored-HauhauCS-Aggressive")
        assert bundle_payload["supports_text"] is True
        assert bundle_payload["supports_vision"] is True
        flat_bundle_payload = next(bundle for bundle in catalog_payload["bundles"] if bundle["bundle_id"] == "Phi-plain-root")
        assert flat_bundle_payload["supports_text"] is True
        assert flat_bundle_payload["supports_vision"] is False

        validation_response = client.get("/api/models/catalog/validation")
        assert validation_response.status_code == 200
        validation_payload = validation_response.json()
        assert validation_payload["total_bundles"] >= 1
        assert validation_payload["invalid_bundle_count"] >= 1
        gemma_validation = next(item for item in validation_payload["bundles"] if item["bundle_id"] == "Gemma-4-E4B-Uncensored-HauhauCS-Aggressive")
        assert gemma_validation["valid"] is False
        assert "text:too_small" in gemma_validation["issues"]
        assert "text:invalid_gguf_header" in gemma_validation["issues"]

        runtime_status_response = client.get("/api/models/runtime/status")
        assert runtime_status_response.status_code == 200
        runtime_status = runtime_status_response.json()
        assert runtime_status["runtime_adapter_status"] == "wired"
        assert "binding_version" in runtime_status

        selection_response = client.patch(
            "/api/models/selection",
            json={"text_provider": "local", "text_bundle_id": "Gemma-4-E4B-Uncensored-HauhauCS-Aggressive"},
        )
        assert selection_response.status_code == 200
        assert selection_response.json()["selection"]["text_bundle_id"] == "Gemma-4-E4B-Uncensored-HauhauCS-Aggressive"

        vision_selection_response = client.patch(
            "/api/models/selection",
            json={"vision_provider": "local", "vision_bundle_id": "Gemma-4-E4B-Uncensored-HauhauCS-Aggressive"},
        )
        assert vision_selection_response.status_code == 200
        assert vision_selection_response.json()["selection"]["vision_bundle_id"] == "Gemma-4-E4B-Uncensored-HauhauCS-Aggressive"

        runtime_text_response = client.post(
            "/api/models/runtime/text",
            json={"prompt": "Resume el runtime local seleccionado."},
        )
        assert runtime_text_response.status_code == 200
        runtime_text_payload = runtime_text_response.json()
        assert runtime_text_payload["provider"] == "local"
        assert runtime_text_payload["ok"] is False

        runtime_vision_response = client.post(
            "/api/models/runtime/vision",
            data={"prompt": "Describe la imagen."},
            files={"image": ("sample.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        )
        assert runtime_vision_response.status_code == 200
        runtime_vision_payload = runtime_vision_response.json()
        assert runtime_vision_payload["provider"] == "local"
        assert runtime_vision_payload["ok"] is False

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
        message_payload = message_response.json()

        memorize_response = client.post(f"/api/interaction/messages/{message_payload['id']}/memorize")
        assert memorize_response.status_code == 200
        assert memorize_response.json()["ok"] is True

        hide_response = client.delete(f"/api/interaction/messages/{message_payload['id']}")
        assert hide_response.status_code == 200
        assert hide_response.json()["ok"] is True

        hidden_messages_response = client.get("/api/interaction/messages", params={"limit": 5})
        assert hidden_messages_response.status_code == 200
        assert any(item["channel"] == "hidden" for item in hidden_messages_response.json())

        rewind_first = client.post(
            "/api/interaction/messages",
            json={"author": "user", "content": "turno 1", "channel": "chat", "session_id": "rewind-room"},
        )
        rewind_second = client.post(
            "/api/interaction/messages",
            json={"author": "assistant", "content": "turno 2", "channel": "assistant", "session_id": "rewind-room"},
        )
        assert rewind_first.status_code == 200
        assert rewind_second.status_code == 200

        rewind_response = client.post(
            f"/api/interaction/sessions/rewind-room/rewind/{rewind_first.json()['id']}",
        )
        assert rewind_response.status_code == 200
        assert rewind_response.json()["rewound"] is True
        assert rewind_response.json()["removed"] >= 1

        sessions_response = client.get("/api/interaction/sessions", params={"limit": 20})
        assert sessions_response.status_code == 200
        sessions_payload = sessions_response.json()
        assert any(item["session_id"] == "rewind-room" for item in sessions_payload)

        session_messages_response = client.get("/api/interaction/sessions/rewind-room/messages", params={"limit": 20})
        assert session_messages_response.status_code == 200
        assert any(message["session_id"] == "rewind-room" for message in session_messages_response.json())

        summary_response = client.get("/api/interaction/summary", params={"limit": 5})
        assert summary_response.status_code == 200
        summary_payload = summary_response.json()
        assert summary_payload["message_count"] >= 1
        assert summary_payload["channel_counts"]["chat"] >= 1
        assert summary_payload["channel_counts"]["hidden"] >= 1
        assert summary_payload["knowledge_overview"]["item_count"] >= 2

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

        csv_payload = (
            "nombre,prompt,reglas,temperatura,top_p,max_tokens,ejemplos\n"
            "Atlas,Actualizado por CSV,regla uno|regla dos,0.55,0.9,1536,Hola|Seguimos\n"
            "Nyx,Perfil de analisis,coherencia|precision,0.65,0.92,1408,Analizo|Resumen\n"
        ).encode("utf-8")
        import_response = client.post(
            "/api/knowledge/engrams/import/csv",
            data={"overwrite_existing": "true"},
            files={"file": ("engrams.csv", csv_payload, "text/csv")},
        )
        assert import_response.status_code == 200
        import_payload = import_response.json()
        assert import_payload["imported"] == 2
        assert import_payload["created"] == 1
        assert import_payload["updated"] == 1

        imported_engrams_response = client.get("/api/knowledge/engrams", params={"limit": 20})
        assert imported_engrams_response.status_code == 200
        imported_engrams = imported_engrams_response.json()
        assert any(item["name"] == "Nyx" for item in imported_engrams)
        atlas_after_import = next((item for item in imported_engrams if item["name"] == "Atlas"), None)
        assert atlas_after_import is not None
        assert atlas_after_import["behavior_prompt"] == "Actualizado por CSV"
        assert "regla uno" in atlas_after_import["meta_rule"].lower()
        assert "max_tokens_respuesta" not in atlas_after_import

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

        graph_response = client.post(
            "/api/knowledge/context/graph",
            json={
                "raw_text": "@Atlas resume el conocimiento base y el documento",
                "limit": 6,
                "identity_id": None,
                "history": "user: necesito panorama completo",
            },
        )
        assert graph_response.status_code == 200
        graph_payload = graph_response.json()
        assert graph_payload["intent"] in {"mixed", "knowledge", "identity"}
        assert "graph" in graph_payload
        assert len(graph_payload["graph"]["nodes"]) >= 2
        assert len(graph_payload["graph"]["edges"]) >= 1
        assert "primary_topic" in graph_payload

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

        conditions_set = client.put(
            "/api/interaction/sessions/test-room/conditions",
            json={"world_rules": "No romper continuidad. Mantener tono epico sobrio."},
        )
        assert conditions_set.status_code == 200
        assert "No romper continuidad" in conditions_set.json()["world_rules"]

        conditions_get = client.get("/api/interaction/sessions/test-room/conditions")
        assert conditions_get.status_code == 200
        assert "tono epico" in conditions_get.json()["world_rules"]

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
            json={"command": "avanza al siguiente acto", "note": "act:1:checkpoint"},
        )
        assert saga_append_response.status_code == 200
        saga_append_payload = saga_append_response.json()
        assert saga_append_payload["appended"] is True
        assert saga_append_payload["saga"]["command_count"] == 2
        assert saga_append_payload["saga"]["act_history"][-1]["act_id"] == "act-1"
        assert saga_append_payload["saga"]["act_history"][-1]["phase"] == "checkpoint"

        contradiction_append_one = client.post(
            f"/api/operations/sagas/{saga_payload['id']}/commands",
            json={"command": "Atlas vive tras el duelo final", "note": "estado inicial"},
        )
        assert contradiction_append_one.status_code == 200
        assert contradiction_append_one.json()["appended"] is True

        contradiction_append_two = client.post(
            f"/api/operations/sagas/{saga_payload['id']}/commands",
            json={"command": "Atlas muere en el mismo duelo final", "note": "giro conflictivo"},
        )
        assert contradiction_append_two.status_code == 200
        assert contradiction_append_two.json()["appended"] is True

        consistency_response = client.get(f"/api/operations/sagas/{saga_payload['id']}/consistency")
        assert consistency_response.status_code == 200
        consistency_payload = consistency_response.json()
        assert consistency_payload["found"] is True
        assert consistency_payload["timeline_conflict_count"] >= 1
        assert consistency_payload["coherence_score"] < 1.0
        assert consistency_payload["retcon_suggestion"]

        retcon_preview_response = client.post(
            f"/api/operations/sagas/{saga_payload['id']}/retcon",
            json={"apply": False},
        )
        assert retcon_preview_response.status_code == 200
        retcon_preview_payload = retcon_preview_response.json()
        assert retcon_preview_payload["applied"] is False
        assert retcon_preview_payload["retcon"]

        retcon_apply_response = client.post(
            f"/api/operations/sagas/{saga_payload['id']}/retcon",
            json={"apply": True},
        )
        assert retcon_apply_response.status_code == 200
        retcon_apply_payload = retcon_apply_response.json()
        assert retcon_apply_payload["applied"] is True
        assert retcon_apply_payload["result"]["appended"] is True

        saga_debate_response = client.post(
            f"/api/operations/sagas/{saga_payload['id']}/debate",
            json={
                "topic": "Debatir el conflicto principal y alternativas del antagonista",
                "note": "act:1:post-close usar tono epico y consistente",
                "identity_name": "Atlas",
                "persist_memory": True,
            },
        )
        assert saga_debate_response.status_code == 200
        saga_debate_payload = saga_debate_response.json()
        assert saga_debate_payload["debated"] is True
        assert saga_debate_payload["saga"]["command_count"] >= 6
        assert saga_debate_payload["memory"]["title"].startswith("Debate saga")
        assert any(
            entry.get("kind") == "debate"
            and entry.get("act_id") == "act-1"
            and entry.get("phase") == "post-close"
            for entry in saga_debate_payload["saga"]["act_history"]
        )

        saga_next_context_response = client.post(
            f"/api/operations/sagas/{saga_payload['id']}/next-context",
            json={
                "prompt": "duelo final atlas continuidad acto siguiente",
                "window_size": 6,
                "recall_limit": 3,
            },
        )
        assert saga_next_context_response.status_code == 200
        saga_next_context_payload = saga_next_context_response.json()
        assert saga_next_context_payload["found"] is True
        assert saga_next_context_payload["saga_id"] == saga_payload["id"]
        assert isinstance(saga_next_context_payload["baseline_context"], str)
        assert "[CANONICAL]" in saga_next_context_payload["baseline_context"]
        assert "[WINDOW]" in saga_next_context_payload["baseline_context"]
        assert "[DEEP_RECALL]" in saga_next_context_payload["baseline_context"]

        saga_detail_response = client.get(f"/api/operations/sagas/{saga_payload['id']}")
        assert saga_detail_response.status_code == 200
        saga_detail = saga_detail_response.json()
        assert saga_detail["title"] == "Saga Atlas"
        assert saga_detail["command_count"] >= 6
        assert saga_detail["last_command"] in {
            "avanza al siguiente acto",
            "Debatir el conflicto principal y alternativas del antagonista",
        }

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

        saga_complete_response = client.patch(
            f"/api/operations/sagas/{saga_payload['id']}",
            json={"status": "completed"},
        )
        assert saga_complete_response.status_code == 200
        assert saga_complete_response.json()["saga"]["status"] == "completed"

        completed_list_response = client.get(
            "/api/operations/sagas",
            params={"limit": 10, "statuses": "completed"},
        )
        assert completed_list_response.status_code == 200
        completed_list = completed_list_response.json()
        assert any(item["id"] == saga_payload["id"] for item in completed_list)

        append_after_complete_response = client.post(
            f"/api/operations/sagas/{saga_payload['id']}/commands",
            json={"command": "epilogo extendido tras cierre", "note": "post-completion extension"},
        )
        assert append_after_complete_response.status_code == 200
        assert append_after_complete_response.json()["appended"] is True

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
        assert status_after_saga["event_counts"]["operations.saga.debated"] >= 1

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

        graph_again = client_again.post(
            "/api/knowledge/context/graph",
            json={
                "raw_text": "Atlas conecta saga y documento base",
                "limit": 6,
                "identity_id": None,
                "history": "user: quiero mapa completo",
            },
        )
        assert graph_again.status_code == 200
        assert "graph" in graph_again.json()

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
        assert saga_detail_again_payload["command_count"] >= 4

        consistency_again = client_again.get(f"/api/operations/sagas/{saga_payload['id']}/consistency")
        assert consistency_again.status_code == 200
        assert consistency_again.json()["found"] is True

        interaction_messages_response = client_again.get("/api/interaction/messages", params={"limit": 10})
        assert interaction_messages_response.status_code == 200
        interaction_messages_payload = interaction_messages_response.json()
        assert any(message["channel"] in {"chat", "hidden"} for message in interaction_messages_payload)

        interaction_summary_response = client_again.get("/api/interaction/summary", params={"limit": 10})
        assert interaction_summary_response.status_code == 200
        assert interaction_summary_response.json()["message_count"] >= 1

        audit_log_response = client_again.get("/api/operations/audit-log", params={"limit": 100})
        assert audit_log_response.status_code == 200
        audit_log_payload = audit_log_response.json()
        assert any(entry["event_name"] == "knowledge.item.created" for entry in audit_log_payload)
        assert any(entry["event_name"] == "knowledge.document.ingested" for entry in audit_log_payload)
        assert any(entry["event_name"] == "operations.saga.started" for entry in audit_log_payload)
        assert any(entry["event_name"] == "operations.saga.command.appended" for entry in audit_log_payload)
        assert any(entry["event_name"] == "operations.saga.debated" for entry in audit_log_payload)
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


def test_saga_next_context_includes_closed_act_canonical_summary(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        start_response = client.post(
            "/api/operations/sagas",
            json={
                "title": "Saga Continuidad",
                "premise": "Prueba de continuidad entre actos.",
                "initial_command": "Acto inicial de continuidad",
            },
        )
        assert start_response.status_code == 200
        saga_id = start_response.json()["id"]

        summary_command = "[ACT 1 SUMMARY] objetivo=consolidar alianza; coherence=0.92; contradictions=0; hitos=acuerdo sellado"
        append_summary = client.post(
            f"/api/operations/sagas/{saga_id}/commands",
            json={"command": summary_command, "note": "act:1:summary"},
        )
        assert append_summary.status_code == 200
        assert append_summary.json()["appended"] is True

        close_marker = client.post(
            f"/api/operations/sagas/{saga_id}/commands",
            json={"command": "[ACT 1 CLOSE] coherencia=0.92 contradicciones=0", "note": "act:1:close"},
        )
        assert close_marker.status_code == 200
        assert close_marker.json()["appended"] is True

        next_context_response = client.post(
            f"/api/operations/sagas/{saga_id}/next-context",
            json={
                "prompt": "arranca el acto 2 manteniendo la continuidad",
                "window_size": 6,
                "recall_limit": 3,
            },
        )
        assert next_context_response.status_code == 200
        payload = next_context_response.json()
        assert payload["found"] is True
        assert payload["canonical_summary"].startswith("[ACT 1 SUMMARY]")
        assert summary_command in payload["baseline_context"]


def test_saga_next_context_recovers_out_of_window_reference(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        start_response = client.post(
            "/api/operations/sagas",
            json={
                "title": "Saga Recall Profundo",
                "premise": "Validar recuperacion fuera de ventana.",
                "initial_command": "prologo breve",
            },
        )
        assert start_response.status_code == 200
        saga_id = start_response.json()["id"]

        old_fact = "La reliquia omega queda oculta en la torre norte"
        old_fact_response = client.post(
            f"/api/operations/sagas/{saga_id}/commands",
            json={"command": old_fact, "note": "act:1:fact"},
        )
        assert old_fact_response.status_code == 200
        assert old_fact_response.json()["appended"] is True

        for index in range(10):
            filler_response = client.post(
                f"/api/operations/sagas/{saga_id}/commands",
                json={"command": f"evento secundario {index}", "note": "act:2:progress"},
            )
            assert filler_response.status_code == 200
            assert filler_response.json()["appended"] is True

        next_context_response = client.post(
            f"/api/operations/sagas/{saga_id}/next-context",
            json={
                "prompt": "recuerda donde estaba la reliquia omega para el acto final",
                "window_size": 4,
                "recall_limit": 3,
            },
        )
        assert next_context_response.status_code == 200
        payload = next_context_response.json()
        assert payload["found"] is True
        assert len(payload["active_window"]) <= 4
        assert any("reliquia omega" in str(item).lower() for item in payload["deep_recall"])
        assert "reliquia omega" in payload["baseline_context"].lower()


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

        saga_response = client.post(
            "/api/operations/sagas",
            json={
                "title": "Saga Realtime",
                "premise": "Integracion de continuidad para chat realtime.",
                "initial_command": "[ACT 1 SUMMARY] objetivo=proteger reliquia omega; coherence=0.9; contradictions=0",
            },
        )
        assert saga_response.status_code == 200
        saga_id = saga_response.json()["id"]

        with client.websocket_connect("/ws/chat") as websocket:
            bootstrap_types: list[str] = []
            realtime_session_id = ""
            for _ in range(8):
                packet = websocket.receive_json()
                bootstrap_types.append(str(packet["type"]))
                if packet["type"] == "session_started":
                    realtime_session_id = str(packet.get("session_id") or "")
                if packet["type"] == "welcome":
                    break

            assert "session_started" in bootstrap_types
            assert "meta_update" in bootstrap_types
            assert "welcome" in bootstrap_types

            websocket.send_json(
                {
                    "content": f"saga_id:{saga_id} Atlas resume la continuidad de saga y la base de conocimiento realtime",
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
            lowered_assistant = assistant_message_text.lower()
            assert "contexto recuperado" not in lowered_assistant
            assert "smoke-doc" not in lowered_assistant
            assert "base de conocimiento realtime" in lowered_assistant or "puntos accionables" in lowered_assistant

        assert realtime_session_id

        memory_response = client.get(f"/api/interaction/sessions/{realtime_session_id}/memory", params={"limit": 20})
        assert memory_response.status_code == 200
        memory_payload = memory_response.json()
        assert memory_payload["session_id"] == realtime_session_id
        assert memory_payload["summary_text"]
        assert memory_payload["last_turn_id"]

        topics_response = client.get(f"/api/interaction/sessions/{realtime_session_id}/topics", params={"limit": 20})
        assert topics_response.status_code == 200
        topics_payload = topics_response.json()
        assert topics_payload["session_id"] == realtime_session_id
        assert isinstance(topics_payload["edges"], list)

        metrics_response = client.get(f"/api/interaction/sessions/{realtime_session_id}/metrics", params={"limit": 20})
        assert metrics_response.status_code == 200
        metrics_payload = metrics_response.json()
        assert len(metrics_payload) >= 1
        assert any(metric["session_id"] == realtime_session_id for metric in metrics_payload)
        metric_for_session = next(metric for metric in metrics_payload if metric["session_id"] == realtime_session_id)
        assert "quality_flags" in metric_for_session
        assert isinstance(metric_for_session["quality_flags"], dict)
        assert "fallback_used" in metric_for_session["quality_flags"]
        assert "timeout_hit" in metric_for_session["quality_flags"]

        traces_response = client.get(
            "/api/admin/context-traces",
            params={"session_id": realtime_session_id, "limit": 20},
        )
        assert traces_response.status_code == 200
        traces_payload = traces_response.json()
        assert isinstance(traces_payload, list)
        assert any(trace["session_id"] == realtime_session_id for trace in traces_payload)
        trace_for_session = next(trace for trace in traces_payload if trace["session_id"] == realtime_session_id)
        assert "quality_flags" in trace_for_session
        assert isinstance(trace_for_session["quality_flags"], dict)
        trace_payload = dict(trace_for_session.get("context_trace") or {})
        saga_trace = dict(trace_payload.get("saga_next_context") or {})
        assert saga_trace.get("saga_id") == saga_id
        assert "canonical_summary" in saga_trace
        assert any((metric.get("coherence_score") or 0) >= 0 for metric in metrics_payload)

        with client.websocket_connect(f"/ws/chat?saga_id={saga_id}") as saga_websocket:
            query_session_id = ""
            while True:
                packet = saga_websocket.receive_json()
                if packet["type"] == "session_started":
                    query_session_id = str(packet.get("session_id") or "")
                if packet["type"] == "welcome":
                    break

            saga_websocket.send_json(
                {
                    "content": "Resume continuidad sin enviar saga_id en el mensaje.",
                    "context_limit": 5,
                    "history_limit": 5,
                }
            )

            while True:
                packet = saga_websocket.receive_json()
                if packet["type"] == "turn_complete":
                    break

        assert query_session_id
        query_traces = client.get(
            "/api/admin/context-traces",
            params={"session_id": query_session_id, "limit": 20},
        )
        assert query_traces.status_code == 200
        query_traces_payload = query_traces.json()
        assert any(trace["session_id"] == query_session_id for trace in query_traces_payload)
        query_trace_for_session = next(trace for trace in query_traces_payload if trace["session_id"] == query_session_id)
        query_trace_payload = dict(query_trace_for_session.get("context_trace") or {})
        query_saga_trace = dict(query_trace_payload.get("saga_next_context") or {})
        assert query_saga_trace.get("saga_id") == saga_id
        query_quality_flags = dict(query_trace_for_session.get("quality_flags") or {})
        assert query_quality_flags.get("saga_context_used") is True

        sse_response = client.post(
            "/api/interaction/stream",
            json={
                "content": "Atlas vuelve a resumir la base de conocimiento realtime",
                "saga_id": saga_id,
                "context_limit": 5,
                "history_limit": 5,
            },
            headers={"x-session-id": "sse-saga-session"},
        )
        assert sse_response.status_code == 200
        sse_text = sse_response.text
        assert "event: session_started" in sse_text
        assert "event: turn_complete" in sse_text
        assert "assistant_message" in sse_text

        sse_traces = client.get(
            "/api/admin/context-traces",
            params={"session_id": "sse-saga-session", "limit": 20},
        )
        assert sse_traces.status_code == 200
        sse_traces_payload = sse_traces.json()
        assert any(trace.get("session_id") == "sse-saga-session" for trace in sse_traces_payload)
        sse_trace_row = next(trace for trace in sse_traces_payload if trace.get("session_id") == "sse-saga-session")
        sse_trace_payload = dict(sse_trace_row.get("context_trace") or {})
        sse_saga_trace = dict(sse_trace_payload.get("saga_next_context") or {})
        assert sse_saga_trace.get("saga_id") == saga_id
        assert sse_saga_trace.get("used") is True

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
            ("base de conocimiento realtime" in str(message["content"]).lower())
            or ("puntos accionables" in str(message["content"]).lower())
            for message in messages
            if message["channel"] == "assistant"
        )

        summary_response = client_again.get("/api/interaction/summary", params={"limit": 50})
        assert summary_response.status_code == 200
        summary_payload = summary_response.json()
        assert summary_payload["channel_counts"]["assistant"] >= 2

        memory_again = client_again.get(f"/api/interaction/sessions/{realtime_session_id}/memory", params={"limit": 20})
        assert memory_again.status_code == 200
        assert memory_again.json()["summary_text"]

        topics_again = client_again.get(f"/api/interaction/sessions/{realtime_session_id}/topics", params={"limit": 20})
        assert topics_again.status_code == 200
        assert isinstance(topics_again.json()["edges"], list)

        metrics_again = client_again.get(f"/api/interaction/sessions/{realtime_session_id}/metrics", params={"limit": 20})
        assert metrics_again.status_code == 200
        assert len(metrics_again.json()) >= 1


def test_delete_session_purges_related_interaction_data(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)
    session_id = "delete-room"

    with TestClient(app) as client:
        seed_user = client.post(
            "/api/interaction/messages",
            json={"author": "user", "content": "Mensaje semilla", "channel": "chat", "session_id": session_id},
        )
        assert seed_user.status_code == 200

        set_conditions = client.put(
            f"/api/interaction/sessions/{session_id}/conditions",
            json={"world_rules": "Regla temporal para borrar."},
        )
        assert set_conditions.status_code == 200

        with client.websocket_connect(f"/ws/chat?session_id={session_id}") as websocket:
            while True:
                packet = websocket.receive_json()
                if packet["type"] == "welcome":
                    break

            websocket.send_json(
                {
                    "content": "Genera trazas y metricas para este chat",
                    "context_limit": 5,
                    "history_limit": 5,
                }
            )

            while True:
                packet = websocket.receive_json()
                if packet["type"] == "turn_complete":
                    break

        delete_response = client.delete(f"/api/interaction/sessions/{session_id}")
        assert delete_response.status_code == 200
        delete_payload = delete_response.json()
        assert delete_payload["deleted"] is True
        assert delete_payload["soft_deleted"] is True
        assert delete_payload["removed_total"] >= 1

        deleted_sessions_response = client.get("/api/interaction/sessions/deleted", params={"limit": 20})
        assert deleted_sessions_response.status_code == 200
        deleted_sessions_payload = deleted_sessions_response.json()
        assert any(str(row.get("session_id", "")) == session_id for row in deleted_sessions_payload)

        messages_response = client.get(f"/api/interaction/sessions/{session_id}/messages", params={"limit": 50})
        assert messages_response.status_code == 200
        assert messages_response.json() == []

        memory_response = client.get(f"/api/interaction/sessions/{session_id}/memory", params={"limit": 20})
        assert memory_response.status_code == 200
        memory_payload = memory_response.json()
        assert memory_payload["summary_text"] == ""
        assert memory_payload["last_turn_id"] is None

        topics_response = client.get(f"/api/interaction/sessions/{session_id}/topics", params={"limit": 20})
        assert topics_response.status_code == 200
        topics_payload = topics_response.json()
        assert topics_payload["primary_topic"] == ""
        assert topics_payload["secondary_topics"] == []

        metrics_response = client.get(f"/api/interaction/sessions/{session_id}/metrics", params={"limit": 20})
        assert metrics_response.status_code == 200
        assert metrics_response.json() == []

        conditions_response = client.get(f"/api/interaction/sessions/{session_id}/conditions")
        assert conditions_response.status_code == 200
        assert conditions_response.json()["world_rules"] == ""

        restore_response = client.post(f"/api/interaction/sessions/{session_id}/restore")
        assert restore_response.status_code == 200
        restore_payload = restore_response.json()
        assert restore_payload["restored"] is True

        restored_messages = client.get(f"/api/interaction/sessions/{session_id}/messages", params={"limit": 50})
        assert restored_messages.status_code == 200
        assert len(restored_messages.json()) >= 1

        hard_delete_response = client.delete(f"/api/interaction/sessions/{session_id}", params={"hard": "true"})
        assert hard_delete_response.status_code == 200
        hard_delete_payload = hard_delete_response.json()
        assert hard_delete_payload["deleted"] is True
        assert hard_delete_payload["hard_deleted"] is True


def test_realtime_greeting_reply_avoids_internal_scaffolding(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/chat") as websocket:
            while True:
                packet = websocket.receive_json()
                if packet["type"] == "welcome":
                    break

            websocket.send_json(
                {
                    "content": "hola",
                    "context_limit": 5,
                    "history_limit": 5,
                }
            )

            assistant_message_text = ""
            while True:
                packet = websocket.receive_json()
                if packet["type"] == "assistant_message":
                    assistant_message_text = str(packet["message"]["content"])
                if packet["type"] == "turn_complete":
                    break

            lowered = assistant_message_text.lower()
            assert assistant_message_text
            assert "analyze the request" not in lowered
            assert "drafting the response" not in lowered
            assert "[context routing]" not in lowered
            assert "[relevant engrams]" not in lowered
            assert len(assistant_message_text) < 180


def test_realtime_identity_question_avoids_scaffolding(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/chat") as websocket:
            while True:
                packet = websocket.receive_json()
                if packet["type"] == "welcome":
                    break

            websocket.send_json(
                {
                    "content": "Hola, Sabes quien eres?",
                    "context_limit": 5,
                    "history_limit": 5,
                }
            )

            assistant_message_text = ""
            while True:
                packet = websocket.receive_json()
                if packet["type"] == "assistant_message":
                    assistant_message_text = str(packet["message"]["content"])
                if packet["type"] == "turn_complete":
                    break

            lowered = assistant_message_text.lower()
            assert assistant_message_text
            assert "analyze the request" not in lowered
            assert "drafting the response" not in lowered
            assert "[context routing]" not in lowered
            assert "[relevant engrams]" not in lowered
            assert "soy" in lowered
            assert "asistente" in lowered