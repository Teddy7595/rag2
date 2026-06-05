from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from app.core.database import DatabaseManager
from app.interaction.adapters.persistence.models import ConversationMessageRecord
from app.interaction.adapters.persistence.models import DeletedSessionRecord
from app.interaction.adapters.persistence.models import IdeaClipRecord
from app.interaction.adapters.persistence.models import SessionMemorySnapshotRecord
from app.interaction.adapters.persistence.models import SessionConditionsRecord
from app.interaction.adapters.persistence.models import SessionTopicGraphRecord
from app.interaction.adapters.persistence.models import TurnCoherenceMetricRecord
from app.interaction.application.ports import InteractionMessageRepositoryPort
from app.interaction.domain import ConversationMessage, IdeaClip


class SqlAlchemyInteractionMessageRepository(InteractionMessageRepositoryPort):
    _DEFAULT_TRASH_RETENTION_HOURS = 24

    def __init__(self, database: DatabaseManager, trash_retention_hours: int | None = None) -> None:
        self.database = database
        if trash_retention_hours is None:
            self._configured_trash_retention_hours = self._DEFAULT_TRASH_RETENTION_HOURS
        else:
            self._configured_trash_retention_hours = max(1, min(168, int(trash_retention_hours)))

    def _trash_retention_hours(self) -> int:
        return self._configured_trash_retention_hours

    @staticmethod
    def _serialize_datetime(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def save(self, message: ConversationMessage) -> ConversationMessage:
        record = ConversationMessageRecord.from_domain(message)
        with self.database.session_scope() as session:
            persisted = session.merge(record)
            session.flush()
            return persisted.to_domain()

    def get_by_id(self, message_id: str) -> ConversationMessage | None:
        with self.database.session_factory() as session:
            record = session.get(ConversationMessageRecord, message_id)
            if not record:
                return None
            return record.to_domain()

    def list_recent(self, limit: int = 20) -> list[ConversationMessage]:
        if limit <= 0:
            return []

        with self.database.session_factory() as session:
            statement = (
                select(ConversationMessageRecord)
                .order_by(ConversationMessageRecord.created_at.desc(), ConversationMessageRecord.id.desc())
                .limit(limit)
            )
            records = session.scalars(statement).all()
            return [record.to_domain() for record in reversed(records)]

    def list_sessions(self, limit: int = 20) -> list[dict[str, object]]:
        if limit <= 0:
            return []

        safe_limit = max(1, min(int(limit), 200))
        with self.database.session_factory() as session:
            summary_statement = (
                select(
                    ConversationMessageRecord.session_id,
                    func.count().label("message_count"),
                    func.max(ConversationMessageRecord.created_at).label("last_message_at"),
                )
                .where(ConversationMessageRecord.session_id.is_not(None))
                .group_by(ConversationMessageRecord.session_id)
                .order_by(func.max(ConversationMessageRecord.created_at).desc())
                .limit(safe_limit)
            )
            summary_rows = session.execute(summary_statement).all()

            result: list[dict[str, object]] = []
            included_ids: set[str] = set()
            for row in summary_rows:
                session_id = str(row.session_id or "").strip()
                if not session_id:
                    continue

                last_message_statement = (
                    select(ConversationMessageRecord)
                    .where(ConversationMessageRecord.session_id == session_id)
                    .order_by(ConversationMessageRecord.created_at.desc(), ConversationMessageRecord.id.desc())
                    .limit(1)
                )
                last_record = session.scalar(last_message_statement)
                last_content = str(last_record.content or "") if last_record else ""

                result.append(
                    {
                        "session_id": session_id,
                        "message_count": int(row.message_count or 0),
                        "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
                        "last_author": str(last_record.author or "") if last_record else "",
                        "last_channel": str(last_record.channel or "") if last_record else "",
                        "last_excerpt": (last_content[:180] + "...") if len(last_content) > 180 else last_content,
                    }
                )
                included_ids.add(session_id)

            fallback_activity: dict[str, datetime] = {}

            conditions_rows = session.execute(
                select(SessionConditionsRecord.session_id, SessionConditionsRecord.updated_at)
                .order_by(SessionConditionsRecord.updated_at.desc())
                .limit(safe_limit * 2)
            ).all()
            for row in conditions_rows:
                key = str(row.session_id or "").strip()
                if not key or key in included_ids:
                    continue
                updated_at = self._as_utc(row.updated_at)
                if updated_at is not None:
                    fallback_activity[key] = max(updated_at, fallback_activity.get(key, updated_at))

            memory_rows = session.execute(
                select(SessionMemorySnapshotRecord.session_id, SessionMemorySnapshotRecord.updated_at)
                .order_by(SessionMemorySnapshotRecord.updated_at.desc())
                .limit(safe_limit * 2)
            ).all()
            for row in memory_rows:
                key = str(row.session_id or "").strip()
                if not key or key in included_ids:
                    continue
                updated_at = self._as_utc(row.updated_at)
                if updated_at is not None:
                    fallback_activity[key] = max(updated_at, fallback_activity.get(key, updated_at))

            graph_rows = session.execute(
                select(SessionTopicGraphRecord.session_id, SessionTopicGraphRecord.updated_at)
                .order_by(SessionTopicGraphRecord.updated_at.desc())
                .limit(safe_limit * 2)
            ).all()
            for row in graph_rows:
                key = str(row.session_id or "").strip()
                if not key or key in included_ids:
                    continue
                updated_at = self._as_utc(row.updated_at)
                if updated_at is not None:
                    fallback_activity[key] = max(updated_at, fallback_activity.get(key, updated_at))

            for session_id, updated_at in sorted(fallback_activity.items(), key=lambda item: item[1], reverse=True):
                if len(result) >= safe_limit:
                    break
                result.append(
                    {
                        "session_id": session_id,
                        "message_count": 0,
                        "last_message_at": updated_at.isoformat() if updated_at else None,
                        "last_author": "",
                        "last_channel": "",
                        "last_excerpt": "Sesion iniciada sin mensajes persistidos aun.",
                    }
                )
                included_ids.add(session_id)

            return result

    def list_deleted_sessions(self, limit: int = 20) -> list[dict[str, object]]:
        if limit <= 0:
            return []

        safe_limit = max(1, min(int(limit), 200))
        now = self._as_utc(datetime.now(timezone.utc))
        assert now is not None
        with self.database.session_scope() as session:
            statement = (
                select(DeletedSessionRecord)
                .order_by(DeletedSessionRecord.deleted_at.desc(), DeletedSessionRecord.session_id.desc())
                .limit(safe_limit)
            )
            records = list(session.scalars(statement).all())
            expired = [record for record in records if (self._as_utc(record.expires_at) or now) <= now]
            for record in expired:
                session.delete(record)
            if expired:
                session.flush()
                records = [record for record in records if record not in expired]

        payload: list[dict[str, object]] = []
        for record in records:
            snapshot = dict(record.payload or {})
            messages = list(snapshot.get("messages") or [])
            last = messages[-1] if messages else {}
            last_content = str((dict(last).get("content") or "")).strip() if isinstance(last, dict) else ""
            payload.append(
                {
                    "session_id": record.session_id,
                    "deleted_at": record.deleted_at.isoformat() if record.deleted_at else None,
                    "expires_at": record.expires_at.isoformat() if record.expires_at else None,
                    "message_count": len(messages),
                    "last_author": str((dict(last).get("author") or "")) if isinstance(last, dict) else "",
                    "last_excerpt": (last_content[:180] + "...") if len(last_content) > 180 else last_content,
                }
            )
        return payload

    def list_session_messages(self, session_id: str, limit: int = 20) -> list[ConversationMessage]:
        if limit <= 0:
            return []

        key = str(session_id or "").strip()
        if not key:
            return []

        with self.database.session_factory() as session:
            statement = (
                select(ConversationMessageRecord)
                .where(ConversationMessageRecord.session_id == key)
                .order_by(ConversationMessageRecord.created_at.desc(), ConversationMessageRecord.id.desc())
                .limit(limit)
            )
            records = session.scalars(statement).all()
            return [record.to_domain() for record in reversed(records)]

    def hide_message(self, message_id: str) -> ConversationMessage | None:
        with self.database.session_scope() as session:
            record = session.get(ConversationMessageRecord, message_id)
            if not record:
                return None
            record.content = "[mensaje oculto por operador]"
            record.channel = "hidden"
            session.flush()
            return record.to_domain()

    def rewind_session(self, session_id: str, message_id: str) -> dict[str, object]:
        with self.database.session_scope() as session:
            anchor = session.get(ConversationMessageRecord, message_id)
            if not anchor or str(anchor.session_id or "") != session_id:
                return {"rewound": False, "session_id": session_id, "message_id": message_id, "removed": 0}

            statement = select(ConversationMessageRecord).where(ConversationMessageRecord.session_id == session_id)
            records = list(session.scalars(statement).all())
            records.sort(key=lambda item: (item.created_at, item.id))
            anchor_index = next((index for index, item in enumerate(records) if item.id == anchor.id), -1)
            if anchor_index < 0:
                return {"rewound": False, "session_id": session_id, "message_id": message_id, "removed": 0}

            removed = 0
            for record in records[anchor_index + 1 :]:
                session.delete(record)
                removed += 1

            session.flush()
            return {
                "rewound": True,
                "session_id": session_id,
                "message_id": message_id,
                "removed": removed,
            }

    def delete_session(self, session_id: str, *, hard_delete: bool = False) -> dict[str, object]:
        key = str(session_id or "").strip()
        if not key:
            return {
                "deleted": False,
                "session_id": key,
                "removed": {
                    "messages": 0,
                    "turn_metrics": 0,
                    "session_memory": 0,
                    "session_topic_graph": 0,
                    "session_conditions": 0,
                },
                "removed_total": 0,
            }

        def _deleted_count(result: object) -> int:
            value = getattr(result, "rowcount", 0)
            if isinstance(value, int):
                return max(0, value)
            return 0

        with self.database.session_scope() as session:
            retention_hours = self._trash_retention_hours()
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(hours=retention_hours)

            messages_records = list(
                session.scalars(
                    select(ConversationMessageRecord)
                    .where(ConversationMessageRecord.session_id == key)
                    .order_by(ConversationMessageRecord.created_at.asc(), ConversationMessageRecord.id.asc())
                ).all()
            )
            metrics_records = list(
                session.scalars(
                    select(TurnCoherenceMetricRecord)
                    .where(TurnCoherenceMetricRecord.session_id == key)
                    .order_by(TurnCoherenceMetricRecord.created_at.asc(), TurnCoherenceMetricRecord.turn_id.asc())
                ).all()
            )
            memory_record = session.get(SessionMemorySnapshotRecord, key)
            graph_record = session.get(SessionTopicGraphRecord, key)
            conditions_record = session.get(SessionConditionsRecord, key)

            snapshot_payload: dict[str, object] = {
                "messages": [
                    {
                        "id": record.id,
                        "author": record.author,
                        "content": record.content,
                        "channel": record.channel,
                        "session_id": record.session_id,
                        "created_at": self._serialize_datetime(record.created_at),
                        "updated_at": self._serialize_datetime(record.updated_at),
                    }
                    for record in messages_records
                ],
                "turn_metrics": [
                    {
                        "turn_id": record.turn_id,
                        "session_id": record.session_id,
                        "user_input": record.user_input,
                        "assistant_reply": record.assistant_reply,
                        "primary_topic": record.primary_topic,
                        "secondary_topics": list(record.secondary_topics or []),
                        "coherence_score": float(record.coherence_score),
                        "context_trace": dict(record.context_trace or {}),
                        "created_at": self._serialize_datetime(record.created_at),
                    }
                    for record in metrics_records
                ],
                "session_memory": (
                    {
                        "session_id": memory_record.session_id,
                        "summary_text": memory_record.summary_text,
                        "sliding_window_size": int(memory_record.sliding_window_size),
                        "last_turn_id": memory_record.last_turn_id,
                        "coherence_score": float(memory_record.coherence_score),
                        "updated_at": self._serialize_datetime(memory_record.updated_at),
                    }
                    if memory_record
                    else None
                ),
                "session_topic_graph": (
                    {
                        "session_id": graph_record.session_id,
                        "primary_topic": graph_record.primary_topic,
                        "secondary_topics": list(graph_record.secondary_topics or []),
                        "topic_states": dict(graph_record.topic_states or {}),
                        "edges": list(graph_record.edges or []),
                        "updated_at": self._serialize_datetime(graph_record.updated_at),
                    }
                    if graph_record
                    else None
                ),
                "session_conditions": (
                    {
                        "session_id": conditions_record.session_id,
                        "world_rules": conditions_record.world_rules,
                        "updated_at": self._serialize_datetime(conditions_record.updated_at),
                    }
                    if conditions_record
                    else None
                ),
            }

            has_any_data = bool(messages_records or metrics_records or memory_record or graph_record or conditions_record)
            if has_any_data and not hard_delete:
                trash_record = DeletedSessionRecord(
                    session_id=key,
                    payload=snapshot_payload,
                    deleted_at=now,
                    expires_at=expires_at,
                )
                session.merge(trash_record)

            messages_result = session.execute(
                delete(ConversationMessageRecord).where(ConversationMessageRecord.session_id == key)
            )
            metrics_result = session.execute(
                delete(TurnCoherenceMetricRecord).where(TurnCoherenceMetricRecord.session_id == key)
            )
            memory_result = session.execute(
                delete(SessionMemorySnapshotRecord).where(SessionMemorySnapshotRecord.session_id == key)
            )
            graph_result = session.execute(
                delete(SessionTopicGraphRecord).where(SessionTopicGraphRecord.session_id == key)
            )
            conditions_result = session.execute(
                delete(SessionConditionsRecord).where(SessionConditionsRecord.session_id == key)
            )
            trash_result = session.execute(
                delete(DeletedSessionRecord).where(DeletedSessionRecord.session_id == key)
            ) if hard_delete else None
            session.flush()

            removed = {
                "messages": _deleted_count(messages_result),
                "turn_metrics": _deleted_count(metrics_result),
                "session_memory": _deleted_count(memory_result),
                "session_topic_graph": _deleted_count(graph_result),
                "session_conditions": _deleted_count(conditions_result),
                "trash_record": int((trash_result.rowcount or 0) if trash_result is not None else 0),
            }
            removed_total = sum(removed.values())
            return {
                "deleted": removed_total > 0,
                "soft_deleted": (removed_total > 0) and not hard_delete,
                "hard_deleted": (removed_total > 0) and hard_delete,
                "session_id": key,
                "removed": removed,
                "removed_total": removed_total,
                "restore_until": expires_at.isoformat() if removed_total > 0 and not hard_delete else None,
            }

    def restore_session(self, session_id: str) -> dict[str, object]:
        key = str(session_id or "").strip()
        if not key:
            return {"restored": False, "session_id": key, "reason": "invalid_session_id"}

        now = datetime.now(timezone.utc)
        with self.database.session_scope() as session:
            trash = session.get(DeletedSessionRecord, key)
            if not trash:
                return {"restored": False, "session_id": key, "reason": "not_in_trash"}
            expires_at = self._as_utc(trash.expires_at)
            if expires_at and expires_at <= now:
                session.delete(trash)
                session.flush()
                return {"restored": False, "session_id": key, "reason": "trash_expired"}

            snapshot = dict(trash.payload or {})

            for entry in list(snapshot.get("messages") or []):
                if not isinstance(entry, dict):
                    continue
                restored = ConversationMessageRecord(
                    id=str(entry.get("id") or ""),
                    author=str(entry.get("author") or ""),
                    content=str(entry.get("content") or ""),
                    channel=str(entry.get("channel") or "chat"),
                    session_id=str(entry.get("session_id") or key),
                    created_at=self._parse_datetime(entry.get("created_at")) or now,
                    updated_at=self._parse_datetime(entry.get("updated_at")) or now,
                )
                session.merge(restored)

            for entry in list(snapshot.get("turn_metrics") or []):
                if not isinstance(entry, dict):
                    continue
                restored = TurnCoherenceMetricRecord(
                    turn_id=str(entry.get("turn_id") or ""),
                    session_id=str(entry.get("session_id") or key),
                    user_input=str(entry.get("user_input") or ""),
                    assistant_reply=str(entry.get("assistant_reply") or ""),
                    primary_topic=str(entry.get("primary_topic") or ""),
                    secondary_topics=list(entry.get("secondary_topics") or []),
                    coherence_score=float(entry.get("coherence_score") or 0.0),
                    context_trace=dict(entry.get("context_trace") or {}),
                    created_at=self._parse_datetime(entry.get("created_at")) or now,
                )
                session.merge(restored)

            memory = snapshot.get("session_memory")
            if isinstance(memory, dict):
                session.merge(
                    SessionMemorySnapshotRecord(
                        session_id=str(memory.get("session_id") or key),
                        summary_text=str(memory.get("summary_text") or ""),
                        sliding_window_size=max(1, int(memory.get("sliding_window_size") or 20)),
                        last_turn_id=(str(memory.get("last_turn_id") or "") or None),
                        coherence_score=float(memory.get("coherence_score") or 0.0),
                        updated_at=self._parse_datetime(memory.get("updated_at")) or now,
                    )
                )

            graph = snapshot.get("session_topic_graph")
            if isinstance(graph, dict):
                session.merge(
                    SessionTopicGraphRecord(
                        session_id=str(graph.get("session_id") or key),
                        primary_topic=str(graph.get("primary_topic") or ""),
                        secondary_topics=list(graph.get("secondary_topics") or []),
                        topic_states=dict(graph.get("topic_states") or {}),
                        edges=list(graph.get("edges") or []),
                        updated_at=self._parse_datetime(graph.get("updated_at")) or now,
                    )
                )

            conditions = snapshot.get("session_conditions")
            if isinstance(conditions, dict):
                session.merge(
                    SessionConditionsRecord(
                        session_id=str(conditions.get("session_id") or key),
                        world_rules=str(conditions.get("world_rules") or ""),
                        updated_at=self._parse_datetime(conditions.get("updated_at")) or now,
                    )
                )

            session.delete(trash)
            session.flush()
            return {
                "restored": True,
                "session_id": key,
                "restored_counts": {
                    "messages": len(list(snapshot.get("messages") or [])),
                    "turn_metrics": len(list(snapshot.get("turn_metrics") or [])),
                    "session_memory": 1 if isinstance(snapshot.get("session_memory"), dict) else 0,
                    "session_topic_graph": 1 if isinstance(snapshot.get("session_topic_graph"), dict) else 0,
                    "session_conditions": 1 if isinstance(snapshot.get("session_conditions"), dict) else 0,
                },
            }

    def count(self) -> int:
        with self.database.session_factory() as session:
            total = session.scalar(select(func.count()).select_from(ConversationMessageRecord))
            return int(total or 0)

    def channel_counts(self) -> dict[str, int]:
        with self.database.session_factory() as session:
            statement = (
                select(ConversationMessageRecord.channel, func.count())
                .group_by(ConversationMessageRecord.channel)
                .order_by(ConversationMessageRecord.channel.asc())
            )
            rows = session.execute(statement).all()
            return {channel: int(total) for channel, total in rows}

    def get_session_memory(self, session_id: str) -> dict[str, object] | None:
        with self.database.session_factory() as session:
            record = session.get(SessionMemorySnapshotRecord, session_id)
            if not record:
                return None
            return {
                "session_id": record.session_id,
                "summary_text": record.summary_text,
                "sliding_window_size": int(record.sliding_window_size),
                "last_turn_id": record.last_turn_id,
                "coherence_score": float(record.coherence_score),
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            }

    def save_session_memory(
        self,
        session_id: str,
        *,
        summary_text: str,
        sliding_window_size: int,
        last_turn_id: str | None,
        coherence_score: float,
    ) -> dict[str, object]:
        with self.database.session_scope() as session:
            record = SessionMemorySnapshotRecord(
                session_id=session_id,
                summary_text=summary_text,
                sliding_window_size=max(1, int(sliding_window_size)),
                last_turn_id=last_turn_id,
                coherence_score=float(coherence_score),
            )
            persisted = session.merge(record)
            session.flush()
            return {
                "session_id": persisted.session_id,
                "summary_text": persisted.summary_text,
                "sliding_window_size": int(persisted.sliding_window_size),
                "last_turn_id": persisted.last_turn_id,
                "coherence_score": float(persisted.coherence_score),
                "updated_at": persisted.updated_at.isoformat() if persisted.updated_at else None,
            }

    def get_session_topic_graph(self, session_id: str) -> dict[str, object] | None:
        with self.database.session_factory() as session:
            record = session.get(SessionTopicGraphRecord, session_id)
            if not record:
                return None
            return {
                "session_id": record.session_id,
                "primary_topic": record.primary_topic,
                "secondary_topics": list(record.secondary_topics or []),
                "topic_states": dict(record.topic_states or {}),
                "edges": list(record.edges or []),
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            }

    def save_session_topic_graph(
        self,
        session_id: str,
        *,
        primary_topic: str,
        secondary_topics: list[str],
        topic_states: dict[str, str],
        edges: list[dict[str, object]],
    ) -> dict[str, object]:
        with self.database.session_scope() as session:
            record = SessionTopicGraphRecord(
                session_id=session_id,
                primary_topic=primary_topic,
                secondary_topics=list(secondary_topics),
                topic_states=dict(topic_states),
                edges=list(edges),
            )
            persisted = session.merge(record)
            session.flush()
            return {
                "session_id": persisted.session_id,
                "primary_topic": persisted.primary_topic,
                "secondary_topics": list(persisted.secondary_topics or []),
                "topic_states": dict(persisted.topic_states or {}),
                "edges": list(persisted.edges or []),
                "updated_at": persisted.updated_at.isoformat() if persisted.updated_at else None,
            }

    def save_turn_metric(
        self,
        turn_id: str,
        session_id: str,
        *,
        user_input: str,
        assistant_reply: str,
        primary_topic: str,
        secondary_topics: list[str],
        coherence_score: float,
        context_trace: dict[str, object],
    ) -> dict[str, object]:
        with self.database.session_scope() as session:
            record = TurnCoherenceMetricRecord(
                turn_id=turn_id,
                session_id=session_id,
                user_input=user_input,
                assistant_reply=assistant_reply,
                primary_topic=primary_topic,
                secondary_topics=list(secondary_topics),
                coherence_score=float(coherence_score),
                context_trace=dict(context_trace),
            )
            persisted = session.merge(record)
            session.flush()
            return {
                "turn_id": persisted.turn_id,
                "session_id": persisted.session_id,
                "user_input": persisted.user_input,
                "assistant_reply": persisted.assistant_reply,
                "primary_topic": persisted.primary_topic,
                "secondary_topics": list(persisted.secondary_topics or []),
                "coherence_score": float(persisted.coherence_score),
                "context_trace": dict(persisted.context_trace or {}),
                "created_at": persisted.created_at.isoformat() if persisted.created_at else None,
            }

    def list_turn_metrics(self, session_id: str, limit: int = 20) -> list[dict[str, object]]:
        if limit <= 0:
            return []
        with self.database.session_factory() as session:
            statement = (
                select(TurnCoherenceMetricRecord)
                .where(TurnCoherenceMetricRecord.session_id == session_id)
                .order_by(TurnCoherenceMetricRecord.created_at.desc(), TurnCoherenceMetricRecord.turn_id.desc())
                .limit(limit)
            )
            records = session.scalars(statement).all()
            payload: list[dict[str, object]] = []
            for record in reversed(records):
                context_trace = dict(record.context_trace or {})
                quality = dict(context_trace.get("quality") or {})
                quality_flags: dict[str, object] = {
                    "guard_triggered": bool(quality.get("guard_triggered")),
                    "fallback_used": bool(quality.get("fallback_used")),
                    "timeout_hit": bool(quality.get("timeout_hit")),
                    "leak_detected": bool(quality.get("leak_detected")),
                    "response_too_long": bool(quality.get("response_too_long")),
                    "deadline_ms": int(quality.get("deadline_ms") or 0),
                    "elapsed_ms": int(quality.get("elapsed_ms") or 0),
                    "intent": str(quality.get("intent") or ""),
                    "non_rag_mode": bool(quality.get("non_rag_mode")),
                    "guard_path": str(quality.get("guard_path") or ""),
                    "instruction_echo_stripped": bool(quality.get("instruction_echo_stripped")),
                }
                payload.append(
                    {
                        "turn_id": record.turn_id,
                        "session_id": record.session_id,
                        "user_input": record.user_input,
                        "assistant_reply": record.assistant_reply,
                        "primary_topic": record.primary_topic,
                        "secondary_topics": list(record.secondary_topics or []),
                        "coherence_score": float(record.coherence_score),
                        "context_trace": context_trace,
                        "quality_flags": quality_flags,
                        "created_at": record.created_at.isoformat() if record.created_at else None,
                    }
                )
            return payload

    def list_context_traces(
        self,
        *,
        trace_id: str | None,
        session_id: str | None,
        trigger: str | None,
        limit: int,
    ) -> list[dict[str, object]]:
        safe_limit = max(1, min(500, int(limit)))
        with self.database.session_factory() as session:
            statement = (
                select(TurnCoherenceMetricRecord)
                .order_by(TurnCoherenceMetricRecord.created_at.desc(), TurnCoherenceMetricRecord.turn_id.desc())
                .limit(safe_limit * 3)
            )
            if session_id:
                statement = statement.where(TurnCoherenceMetricRecord.session_id == session_id)
            if trace_id:
                statement = statement.where(TurnCoherenceMetricRecord.turn_id == trace_id)
            records = list(session.scalars(statement).all())

        rows: list[dict[str, object]] = []
        trigger_filter = (trigger or "").strip().lower()
        for record in records:
            context_trace = dict(record.context_trace or {})
            intent = str(context_trace.get("intent") or "")
            if trigger_filter and trigger_filter not in intent.lower():
                continue

            quality = dict(context_trace.get("quality") or {})
            quality_flags: dict[str, object] = {
                "guard_triggered": bool(quality.get("guard_triggered")),
                "fallback_used": bool(quality.get("fallback_used")),
                "timeout_hit": bool(quality.get("timeout_hit")),
                "leak_detected": bool(quality.get("leak_detected")),
                "response_too_long": bool(quality.get("response_too_long")),
                "deadline_ms": int(quality.get("deadline_ms") or 0),
                "elapsed_ms": int(quality.get("elapsed_ms") or 0),
                "intent": str(quality.get("intent") or ""),
                "non_rag_mode": bool(quality.get("non_rag_mode")),
                "guard_path": str(quality.get("guard_path") or ""),
                "instruction_echo_stripped": bool(quality.get("instruction_echo_stripped")),
                "saga_context_used": bool(quality.get("saga_context_used")),
            }

            rows.append(
                {
                    "trace_id": record.turn_id,
                    "turn_id": record.turn_id,
                    "session_id": record.session_id,
                    "trigger": intent,
                    "coherence_score": float(record.coherence_score),
                    "primary_topic": record.primary_topic,
                    "secondary_topics": list(record.secondary_topics or []),
                    "context_trace": context_trace,
                    "quality_flags": quality_flags,
                    "created_at": record.created_at.isoformat() if record.created_at else None,
                }
            )
            if len(rows) >= safe_limit:
                break

        rows.reverse()
        return rows

    def get_session_conditions(self, session_id: str) -> dict[str, object] | None:
        with self.database.session_factory() as session:
            record = session.get(SessionConditionsRecord, session_id)
            if not record:
                return None
            return {
                "session_id": record.session_id,
                "world_rules": record.world_rules,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            }

    def save_session_conditions(self, session_id: str, *, world_rules: str) -> dict[str, object]:
        with self.database.session_scope() as session:
            record = SessionConditionsRecord(session_id=session_id, world_rules=world_rules.strip())
            persisted = session.merge(record)
            session.flush()
            return {
                "session_id": persisted.session_id,
                "world_rules": persisted.world_rules,
                "updated_at": persisted.updated_at.isoformat() if persisted.updated_at else None,
            }

    # ------------------------------------------------------------------
    # IdeaClip (librito de ideas)
    # ------------------------------------------------------------------

    def save_idea_clip(self, clip: IdeaClip) -> IdeaClip:
        record = IdeaClipRecord.from_domain(clip)
        with self.database.session_scope() as session:
            persisted = session.merge(record)
            session.flush()
            return persisted.to_domain()

    def get_idea_clip(self, clip_id: str) -> IdeaClip | None:
        with self.database.session_factory() as session:
            record = session.get(IdeaClipRecord, clip_id)
            return record.to_domain() if record else None

    def list_idea_clips(self, limit: int = 50, session_id: str | None = None) -> list[IdeaClip]:
        with self.database.session_factory() as session:
            stmt = select(IdeaClipRecord).order_by(IdeaClipRecord.created_at.desc())
            if session_id:
                stmt = stmt.where(IdeaClipRecord.session_id == session_id)
            stmt = stmt.limit(limit)
            records = session.scalars(stmt).all()
            return [r.to_domain() for r in records]

    def delete_idea_clip(self, clip_id: str) -> bool:
        with self.database.session_scope() as session:
            record = session.get(IdeaClipRecord, clip_id)
            if not record:
                return False
            session.delete(record)
            return True