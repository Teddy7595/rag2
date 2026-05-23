from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.bootstrap import create_app


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

        current_identity_response = client.get("/api/knowledge/identity/current")
        assert current_identity_response.status_code == 200
        assert current_identity_response.json()["name"] == "Atlas"

        hints_response = client.get("/api/knowledge/identity/hints")
        assert hints_response.status_code == 200
        assert "@Atlas" in hints_response.json()

        status_response = client.get("/api/operations/status", params={"limit": 10})
        assert status_response.status_code == 200
        status_payload = status_response.json()
        assert status_payload["captured_events"] >= 5
        assert status_payload["event_counts"]["knowledge.item.created"] >= 1
        assert status_payload["event_counts"]["interaction.message.recorded"] >= 1
        assert status_payload["event_counts"]["knowledge.engram.changed"] >= 2
        assert status_payload["event_counts"]["knowledge.identity.resolved"] >= 1

    app_again = build_test_app(tmp_path, monkeypatch)

    with TestClient(app_again) as client_again:
        knowledge_items_response = client_again.get("/api/knowledge/items", params={"limit": 10})
        assert knowledge_items_response.status_code == 200
        assert any(item["title"] == "Primer conocimiento" for item in knowledge_items_response.json())

        engrams_response = client_again.get("/api/knowledge/engrams", params={"limit": 10})
        assert engrams_response.status_code == 200
        assert any(item["name"] == "Atlas" for item in engrams_response.json())

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

        audit_log_response = client_again.get("/api/operations/audit-log", params={"limit": 10})
        assert audit_log_response.status_code == 200
        assert any(entry["event_name"] == "knowledge.item.created" for entry in audit_log_response.json())