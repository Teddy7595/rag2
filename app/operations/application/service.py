from __future__ import annotations

from typing import Any
import re

from app.core.events import EventBus
from app.core.events import EventEnvelope
from app.operations.application.ports import AuditLogRepositoryPort
from app.operations.application.ports import SagaWorkflowRepositoryPort
from app.operations.domain import OperationAuditEntry
from app.operations.domain import SagaWorkflow


class OperationsService:
    def __init__(
        self,
        repository: AuditLogRepositoryPort,
        event_bus: EventBus,
        saga_repository: SagaWorkflowRepositoryPort | None = None,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.saga_repository = saga_repository

    def capture_domain_event(self, envelope: EventEnvelope[Any]) -> None:
        self.repository.save(OperationAuditEntry.from_envelope(envelope))

    def status(self, request: OperationsStatusRequest) -> dict[str, object]:
        from app.operations.events import OperationsAuditRequest
        from app.operations.events import OperationsSagaListRequest

        recent_entries = self.list_audit_log(OperationsAuditRequest(limit=request.limit))
        recent_sagas = self.list_sagas(OperationsSagaListRequest(limit=request.limit))
        return {
            "captured_events": self.repository.count(),
            "recent_entries": recent_entries,
            "event_counts": self.repository.event_counts(),
            "saga_count": self.saga_repository.count() if self.saga_repository else 0,
            "recent_sagas": recent_sagas,
        }

    def list_audit_log(self, request: OperationsAuditRequest) -> list[dict[str, object]]:
        if request.limit <= 0:
            return []
        entries = self.repository.list_recent(limit=request.limit)
        return [entry.as_dict() for entry in entries]

    def list_sagas(self, request: OperationsSagaListRequest) -> list[dict[str, object]]:
        saga_repository = self._require_saga_repository()
        if request.limit <= 0:
            return []
        workflows = saga_repository.list_recent(limit=request.limit)
        statuses = tuple(
            status.strip().lower()
            for status in (request.statuses or ())
            if isinstance(status, str) and status.strip()
        )
        if statuses:
            workflows = [workflow for workflow in workflows if str(workflow.status).lower() in statuses]
        return [workflow.as_dict() for workflow in workflows]

    def get_saga(self, request: OperationsSagaDetailRequest) -> dict[str, object]:
        saga_repository = self._require_saga_repository()
        workflow = saga_repository.get_by_id(request.saga_id)
        if not workflow:
            return {"found": False, "saga_id": request.saga_id}
        return workflow.as_dict()

    def start_saga(self, request: OperationsSagaStartRequest) -> dict[str, object]:
        from app.operations.events import PUBLISH_OPERATIONS_SAGA_STARTED

        saga_repository = self._require_saga_repository()
        workflow = SagaWorkflow(
            title=request.title,
            premise=request.premise,
            summary=request.summary or request.premise,
            world_building=request.world_building,
            status="active",
        )
        if request.initial_command.strip():
            workflow.record_command(request.initial_command, note="initial command")
        saved_workflow = saga_repository.save(workflow)
        payload = saved_workflow.as_dict()
        self.event_bus.publish(
            PUBLISH_OPERATIONS_SAGA_STARTED,
            payload,
            source_module="operations.application.service",
            metadata={
                "saga_id": payload["id"],
                "title": payload["title"],
                "command_count": payload["command_count"],
            },
        )
        return payload

    def append_saga_command(self, request: OperationsSagaCommandAppendRequest) -> dict[str, object]:
        from app.operations.events import PUBLISH_OPERATIONS_SAGA_COMMAND_APPENDED

        saga_repository = self._require_saga_repository()
        workflow = saga_repository.get_by_id(request.saga_id)
        if not workflow:
            return {"appended": False, "saga_id": request.saga_id}

        workflow.record_command(request.command, note=request.note)
        saved_workflow = saga_repository.save(workflow)
        payload = saved_workflow.as_dict()
        self.event_bus.publish(
            PUBLISH_OPERATIONS_SAGA_COMMAND_APPENDED,
            {
                "action": "command_appended",
                "command": request.command,
                "note": request.note,
                "saga": payload,
            },
            source_module="operations.application.service",
            metadata={
                "saga_id": payload["id"],
                "command_count": payload["command_count"],
            },
        )
        return {"appended": True, "saga": payload}

    def update_saga(self, request: OperationsSagaUpdateRequest) -> dict[str, object]:
        from app.operations.events import PUBLISH_OPERATIONS_SAGA_UPDATED

        saga_repository = self._require_saga_repository()
        workflow = saga_repository.get_by_id(request.saga_id)
        if not workflow:
            return {"updated": False, "saga_id": request.saga_id}

        if request.title is not None:
            workflow.title = request.title
        if request.premise is not None:
            workflow.premise = request.premise
        if request.summary is not None:
            workflow.summary = request.summary
        if request.status is not None:
            workflow.status = request.status
        if request.world_building is not None:
            workflow.world_building = request.world_building
        workflow.touch()

        saved_workflow = saga_repository.save(workflow)
        payload = saved_workflow.as_dict()
        self.event_bus.publish(
            PUBLISH_OPERATIONS_SAGA_UPDATED,
            {"action": "updated", "saga": payload},
            source_module="operations.application.service",
            metadata={
                "saga_id": payload["id"],
                "status": payload["status"],
            },
        )
        return {"updated": True, "saga": payload}

    def delete_saga(self, request: OperationsSagaDeleteRequest) -> dict[str, object]:
        from app.operations.events import PUBLISH_OPERATIONS_SAGA_DELETED

        saga_repository = self._require_saga_repository()
        workflow = saga_repository.get_by_id(request.saga_id)
        deleted = saga_repository.delete(request.saga_id)
        if deleted:
            payload = workflow.as_dict() if workflow else {"saga_id": request.saga_id}
            self.event_bus.publish(
                PUBLISH_OPERATIONS_SAGA_DELETED,
                {"action": "deleted", "saga": payload},
                source_module="operations.application.service",
                metadata={"saga_id": request.saga_id},
            )
        return {"deleted": deleted, "saga_id": request.saga_id}

    def debate_saga(self, request: OperationsSagaDebateRequest) -> dict[str, object]:
        from app.knowledge.events import KnowledgeItemCreateRequest
        from app.knowledge.events import REQUEST_KNOWLEDGE_ITEM_CREATE
        from app.operations.events import PUBLISH_OPERATIONS_SAGA_DEBATED

        saga_repository = self._require_saga_repository()
        workflow = saga_repository.get_by_id(request.saga_id)
        if not workflow:
            return {"debated": False, "saga_id": request.saga_id}

        debate_topic = request.topic.strip()
        debate_note = request.note.strip()
        if not debate_topic:
            return {
                "debated": False,
                "saga_id": request.saga_id,
                "detail": "Debate topic cannot be empty.",
            }

        workflow.record_command(debate_topic, note=f"debate:{debate_note}" if debate_note else "debate")
        workflow.act_history.append(
            {
                "kind": "debate",
                "topic": debate_topic,
                "note": debate_note,
                "identity_name": request.identity_name,
            }
        )
        workflow.touch()

        saved_workflow = saga_repository.save(workflow)
        memory_payload: dict[str, object] | None = None
        if request.persist_memory:
            safe_identity = (request.identity_name or "System").strip() or "System"
            slug = re.sub(r"[^a-z0-9]+", "-", safe_identity.lower()).strip("-") or "system"
            memory_payload = self.event_bus.request(
                REQUEST_KNOWLEDGE_ITEM_CREATE,
                KnowledgeItemCreateRequest(
                    title=f"Debate saga {saved_workflow.title}",
                    content=(
                        f"Saga: {saved_workflow.title}\n"
                        f"Estado: {saved_workflow.status}\n"
                        f"Engrama: {safe_identity}\n"
                        f"Tema debatido: {debate_topic}\n"
                        f"Nota: {debate_note or 'sin nota'}"
                    ),
                    tags=("saga", "debate", f"engram:{slug}", f"saga:{saved_workflow.id}"),
                ),
                source_module="operations.application.service",
            )

        saga_payload = saved_workflow.as_dict()
        event_payload = {
            "action": "debated",
            "topic": debate_topic,
            "note": debate_note,
            "identity_name": request.identity_name,
            "persist_memory": request.persist_memory,
            "memory": memory_payload,
            "saga": saga_payload,
        }
        self.event_bus.publish(
            PUBLISH_OPERATIONS_SAGA_DEBATED,
            event_payload,
            source_module="operations.application.service",
            metadata={
                "saga_id": saga_payload["id"],
                "status": saga_payload["status"],
                "persist_memory": request.persist_memory,
            },
        )
        return {"debated": True, "saga": saga_payload, "memory": memory_payload}

    def _require_saga_repository(self) -> SagaWorkflowRepositoryPort:
        if not self.saga_repository:
            raise RuntimeError("Saga repository not configured")
        return self.saga_repository