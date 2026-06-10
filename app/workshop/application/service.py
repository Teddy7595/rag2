from __future__ import annotations

from app.core.events import EventBus
from app.knowledge.events import (
    DocumentIngestRequest,
    REQUEST_KNOWLEDGE_DOCUMENT_INGEST,
)
from app.workshop.application.ports import WorkshopRepositoryPort
from app.workshop.domain.entities import WorkshopSession


class WorkshopService:
    def __init__(
        self,
        repository: WorkshopRepositoryPort,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus

    def create_session(
        self,
        title: str,
        engram_id: str,
        source_documents: list[dict],
        chat_session_id: str | None = None,
    ) -> WorkshopSession:
        from uuid import uuid4
        session_id = chat_session_id or str(uuid4())
        ws = WorkshopSession.new(title=title, engram_id=engram_id, chat_session_id=session_id)
        ws.source_documents = list(source_documents)
        return self.repository.save(ws)

    def get_session(self, workshop_id: str) -> WorkshopSession | None:
        return self.repository.get_by_id(workshop_id)

    def get_by_chat_session(self, chat_session_id: str) -> WorkshopSession | None:
        return self.repository.get_by_chat_session(chat_session_id)

    def list_sessions(self, limit: int = 20) -> list[WorkshopSession]:
        return self.repository.list_recent(limit=limit)

    def close_session(self, workshop_id: str) -> WorkshopSession | None:
        ws = self.repository.get_by_id(workshop_id)
        if not ws:
            return None
        ws.close()
        return self.repository.save(ws)

    def promote(
        self,
        workshop_id: str,
        summary_title: str,
        summary_text: str,
    ) -> dict:
        ws = self.repository.get_by_id(workshop_id)
        if not ws:
            return {"ok": False, "detail": "Workshop not found"}

        ingest_result = self.event_bus.request(
            REQUEST_KNOWLEDGE_DOCUMENT_INGEST,
            DocumentIngestRequest(
                title=f"[Taller] {summary_title}",
                raw_text=summary_text,
                source_uri=f"workshop:{workshop_id}",
                tags=("workshop", "promoted"),
            ),
            source_module="workshop.application.service",
        )

        entry_ids: list[str] = []
        if isinstance(ingest_result, dict):
            doc = ingest_result.get("document") or {}
            if doc.get("id"):
                entry_ids.append(str(doc["id"]))
            for chunk in list(ingest_result.get("chunks") or []):
                if isinstance(chunk, dict) and chunk.get("id"):
                    entry_ids.append(str(chunk["id"]))

        ws.promoted_entry_ids = list(ws.promoted_entry_ids) + entry_ids
        if ws.status == "active":
            ws.status = "promoted"
        ws.touch()
        saved = self.repository.save(ws)
        return {
            "ok": True,
            "workshop": saved.as_dict(),
            "promoted_entry_ids": entry_ids,
        }

    def delete_session(self, workshop_id: str) -> bool:
        return self.repository.delete(workshop_id)
