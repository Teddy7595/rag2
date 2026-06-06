from __future__ import annotations

from datetime import datetime
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
            workflow.record_command(request.initial_command, note="initial command", act_id="act-1", phase="seed")
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

        act_id, phase = self._extract_act_marker(request.note, request.command)
        workflow.record_command(request.command, note=request.note, act_id=act_id, phase=phase)
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

    def delete_act(self, request: OperationsSagaActDeleteRequest) -> dict[str, object]:
        saga_repository = self._require_saga_repository()
        workflow = saga_repository.get_by_id(request.saga_id)
        if not workflow:
            return {"deleted": False, "saga_id": request.saga_id}

        act_num = request.act_number
        act_marker_re = re.compile(rf"\[ACT\s+{act_num}\s+(OPEN|CLOSE|SUMMARY)\]", re.IGNORECASE)
        any_open_re = re.compile(r"\[ACT\s+\d+\s+OPEN\]", re.IGNORECASE)

        commands = list(workflow.command_history)
        indices_to_remove: set[int] = set()
        in_target_act = False

        for i, cmd in enumerate(commands):
            if act_marker_re.search(cmd):
                action_match = re.search(r"(OPEN|CLOSE|SUMMARY)", cmd, re.IGNORECASE)
                action = action_match.group(1).upper() if action_match else ""
                indices_to_remove.add(i)
                if action == "OPEN":
                    in_target_act = True
                elif action in ("CLOSE", "SUMMARY"):
                    in_target_act = False
            elif in_target_act:
                if any_open_re.search(cmd):
                    in_target_act = False
                else:
                    indices_to_remove.add(i)

        if not indices_to_remove:
            return {"deleted": False, "saga_id": request.saga_id, "detail": "Act not found"}

        workflow.command_history = [cmd for i, cmd in enumerate(commands) if i not in indices_to_remove]
        act_id_str = f"act-{act_num}"
        workflow.act_history = [
            entry for entry in workflow.act_history
            if str(entry.get("act_id") or "") != act_id_str
        ]
        workflow.touch()
        saved = saga_repository.save(workflow)
        return {"deleted": True, "saga_id": request.saga_id, "act_number": act_num, "saga": saved.as_dict()}

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

        debate_note_tag = f"debate:{debate_note}" if debate_note else "debate"
        act_id, phase = self._extract_act_marker(debate_note_tag, debate_topic)
        workflow.record_command(debate_topic, note=debate_note_tag, act_id=act_id, phase=phase or "debate")
        workflow.act_history.append(
            {
                "kind": "debate",
                "topic": debate_topic,
                "note": debate_note,
                "identity_name": request.identity_name,
                "act_id": act_id,
                "phase": phase or "debate",
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

    def analyze_saga_consistency(self, request: OperationsSagaConsistencyRequest) -> dict[str, object]:
        workflow = self._require_saga_repository().get_by_id(request.saga_id)
        if not workflow:
            return {"found": False, "saga_id": request.saga_id}

        commands = [str(command).strip() for command in workflow.command_history if str(command).strip()]
        semantic_contradictions = self._detect_contradictions(commands)
        timeline_contradictions = self._detect_entity_timeline_contradictions(workflow)
        contradictions = semantic_contradictions + timeline_contradictions
        score = round(max(0.0, 1.0 - (0.18 * len(semantic_contradictions)) - (0.28 * len(timeline_contradictions))), 3)
        suggestion = self._build_retcon_suggestion(workflow.title, contradictions)
        return {
            "found": True,
            "saga_id": workflow.id,
            "title": workflow.title,
            "status": workflow.status,
            "coherence_score": score,
            "contradictions": contradictions,
            "semantic_conflict_count": len(semantic_contradictions),
            "timeline_conflict_count": len(timeline_contradictions),
            "retcon_suggestion": suggestion,
            "command_count": len(workflow.command_history),
        }

    def apply_saga_retcon(self, request: OperationsSagaRetconRequest) -> dict[str, object]:
        from app.operations.events import OperationsSagaCommandAppendRequest
        from app.operations.events import OperationsSagaConsistencyRequest

        analysis = self.analyze_saga_consistency(OperationsSagaConsistencyRequest(saga_id=request.saga_id))
        if not analysis.get("found"):
            return {"applied": False, "saga_id": request.saga_id, "analysis": analysis}

        suggestion = str(analysis.get("retcon_suggestion") or "").strip()
        if not suggestion:
            return {"applied": False, "saga_id": request.saga_id, "analysis": analysis}

        if request.apply:
            appended = self.append_saga_command(
                OperationsSagaCommandAppendRequest(
                    saga_id=request.saga_id,
                    command=suggestion,
                    note="retcon:auto",
                )
            )
            return {
                "applied": bool(appended.get("appended")),
                "saga_id": request.saga_id,
                "retcon": suggestion,
                "analysis": analysis,
                "result": appended,
            }

        return {
            "applied": False,
            "saga_id": request.saga_id,
            "retcon": suggestion,
            "analysis": analysis,
        }

    def build_saga_next_context(self, request: OperationsSagaNextContextRequest) -> dict[str, object]:
        workflow = self._require_saga_repository().get_by_id(request.saga_id)
        if not workflow:
            return {"found": False, "saga_id": request.saga_id}

        commands = [str(command).strip() for command in workflow.command_history if str(command).strip()]
        window_size = max(2, min(24, int(request.window_size or 6)))
        recall_limit = max(1, min(8, int(request.recall_limit or 4)))
        active_window = commands[-window_size:]
        older_commands = commands[:-window_size] if len(commands) > window_size else []

        prompt_tokens = self._tokenize(str(request.prompt or ""))
        ranked_hits: list[tuple[int, str]] = []
        if prompt_tokens and older_commands:
            for command in older_commands:
                command_tokens = self._tokenize(command)
                score = len(prompt_tokens.intersection(command_tokens))
                if score > 0:
                    ranked_hits.append((score, command))
        ranked_hits.sort(key=lambda item: item[0], reverse=True)
        deep_recall = [item[1] for item in ranked_hits[:recall_limit]]

        canonical_summary = self._latest_canonical_summary(commands) or str(workflow.summary or "").strip()
        baseline_lines = [
            f"[CANONICAL] {canonical_summary or 'sin resumen canonico confirmado'}",
            "[WINDOW]",
            *(active_window or ["sin comandos recientes"]),
            "[DEEP_RECALL]",
            *(deep_recall or ["sin hallazgos fuera de ventana"]),
        ]
        baseline_context = "\n".join(baseline_lines)

        return {
            "found": True,
            "saga_id": workflow.id,
            "title": workflow.title,
            "prompt": str(request.prompt or ""),
            "window_size": window_size,
            "recall_limit": recall_limit,
            "canonical_summary": canonical_summary,
            "active_window": active_window,
            "deep_recall": deep_recall,
            "baseline_context": baseline_context,
            "command_count": len(commands),
        }

    def _detect_contradictions(self, commands: list[str]) -> list[dict[str, str]]:
        pairs = [
            ("vive", "muere"),
            ("aliado", "enemigo"),
            ("gana", "pierde"),
            ("paz", "guerra"),
            ("humano", "inmortal"),
        ]
        normalized = [item.lower() for item in commands]
        findings: list[dict[str, str]] = []
        for positive, negative in pairs:
            pos_hits = [(idx, text) for idx, text in enumerate(normalized) if positive in text]
            neg_hits = [(idx, text) for idx, text in enumerate(normalized) if negative in text]
            for pos_index, _ in pos_hits:
                for neg_index, _ in neg_hits:
                    if pos_index == neg_index:
                        continue
                    findings.append(
                        {
                            "type": "semantic_conflict",
                            "positive": positive,
                            "negative": negative,
                            "first_command": commands[min(pos_index, neg_index)],
                            "second_command": commands[max(pos_index, neg_index)],
                        }
                    )
                    break
                if findings and findings[-1].get("positive") == positive:
                    break
        return findings

    def _detect_entity_timeline_contradictions(self, workflow: SagaWorkflow) -> list[dict[str, str]]:
        entity_states: dict[str, dict[str, str]] = {}
        findings: list[dict[str, str]] = []

        for index, act in enumerate(workflow.act_history):
            if not isinstance(act, dict):
                continue
            if str(act.get("kind") or "") != "command":
                continue

            command = str(act.get("command") or "").strip()
            if not command:
                continue
            recorded_at = str(act.get("recorded_at") or "")
            timestamp = self._normalize_timestamp(recorded_at)
            lowered = command.lower()
            entities = self._extract_entities(command)
            if not entities:
                entities = ["global"]

            for entity in entities:
                previous = entity_states.get(entity, {})

                life_state = self._resolve_binary_state(lowered, "alive", ("vive", "nace", "resucita"), ("muere", "fallece"))
                if life_state and previous.get("alive") and previous.get("alive") != life_state:
                    findings.append(
                        {
                            "type": "entity_lifecycle",
                            "entity": entity,
                            "axis": "alive",
                            "previous_state": previous.get("alive", ""),
                            "new_state": life_state,
                            "first_command": previous.get("command", ""),
                            "second_command": command,
                            "first_at": previous.get("recorded_at", ""),
                            "second_at": timestamp,
                        }
                    )
                if life_state:
                    previous["alive"] = life_state

                allegiance_state = self._resolve_binary_state(lowered, "allegiance", ("aliado", "leal", "amigo"), ("enemigo", "traidor", "rival"))
                if allegiance_state and previous.get("allegiance") and previous.get("allegiance") != allegiance_state:
                    findings.append(
                        {
                            "type": "entity_alignment",
                            "entity": entity,
                            "axis": "allegiance",
                            "previous_state": previous.get("allegiance", ""),
                            "new_state": allegiance_state,
                            "first_command": previous.get("command", ""),
                            "second_command": command,
                            "first_at": previous.get("recorded_at", ""),
                            "second_at": timestamp,
                        }
                    )
                if allegiance_state:
                    previous["allegiance"] = allegiance_state

                previous["command"] = command
                previous["recorded_at"] = timestamp
                entity_states[entity] = previous

            if index >= 120:
                break

        return findings

    def _normalize_timestamp(self, value: str) -> str:
        text = (value or "").strip()
        if not text:
            return ""
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return text

    def _extract_entities(self, text: str) -> list[str]:
        entities: list[str] = []
        for match in re.findall(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\b", text):
            if match.lower() in {"el", "la", "los", "las", "un", "una"}:
                continue
            if match not in entities:
                entities.append(match)
        return entities[:5]

    def _resolve_binary_state(
        self,
        lowered_text: str,
        axis: str,
        positive_markers: tuple[str, ...],
        negative_markers: tuple[str, ...],
    ) -> str | None:
        if any(marker in lowered_text for marker in positive_markers):
            return f"{axis}:positive"
        if any(marker in lowered_text for marker in negative_markers):
            return f"{axis}:negative"
        return None

    def _build_retcon_suggestion(self, title: str, contradictions: list[dict[str, str]]) -> str:
        if not contradictions:
            return ""
        first = contradictions[0]
        contradiction_type = str(first.get("type") or "")
        if contradiction_type == "entity_lifecycle":
            return (
                f"Retcon sugerido para '{title}': aclarar que {first.get('entity') or 'el personaje'} "
                "atraviesa una muerte aparente seguida de recuperacion verificable en un acto intermedio."
            )
        if contradiction_type == "entity_alignment":
            return (
                f"Retcon sugerido para '{title}': justificar el cambio de lealtad de "
                f"{first.get('entity') or 'la entidad'} mediante motivacion, presion externa y evidencia en escena."
            )
        return (
            f"Retcon sugerido para '{title}': reconciliar la tension entre "
            f"'{first.get('positive')}' y '{first.get('negative')}' con una causa diegetica explicita "
            "(evento intermedio, identidad encubierta o cambio de perspectiva)."
        )

    def _extract_act_marker(self, note: str, command: str) -> tuple[str | None, str | None]:
        note_text = str(note or "").strip().lower()
        command_text = str(command or "").strip()

        match = re.search(r"act:(\d+)(?::([a-z0-9_-]+))?", note_text)
        if not match:
            match = re.search(r"\[act\s+(\d+)\s+([a-z0-9_-]+)\]", command_text, flags=re.IGNORECASE)

        if not match:
            return None, None

        act_number = match.group(1)
        phase = (match.group(2) or "").strip().lower() or None
        return f"act-{act_number}", phase

    def _tokenize(self, text: str) -> set[str]:
        cleaned = re.sub(r"[^a-z0-9\s]", " ", str(text or "").lower())
        return {item for item in cleaned.split() if len(item) >= 4}

    def _latest_canonical_summary(self, commands: list[str]) -> str:
        for command in reversed(commands):
            value = str(command).strip()
            if value.startswith("[ACT") and "SUMMARY]" in value:
                return value
        return ""

    def _require_saga_repository(self) -> SagaWorkflowRepositoryPort:
        if not self.saga_repository:
            raise RuntimeError("Saga repository not configured")
        return self.saga_repository