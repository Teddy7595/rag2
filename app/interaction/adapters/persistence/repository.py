from __future__ import annotations

from sqlalchemy import func, select

from app.core.database import DatabaseManager
from app.interaction.adapters.persistence.models import ConversationMessageRecord
from app.interaction.adapters.persistence.models import SessionMemorySnapshotRecord
from app.interaction.adapters.persistence.models import SessionConditionsRecord
from app.interaction.adapters.persistence.models import SessionTopicGraphRecord
from app.interaction.adapters.persistence.models import TurnCoherenceMetricRecord
from app.interaction.application.ports import InteractionMessageRepositoryPort
from app.interaction.domain import ConversationMessage


class SqlAlchemyInteractionMessageRepository(InteractionMessageRepositoryPort):
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

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

            return result

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
                quality_flags = {
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
            quality_flags = {
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