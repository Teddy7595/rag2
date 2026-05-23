from __future__ import annotations

from sqlalchemy import func, select

from app.core.database import DatabaseManager
from app.interaction.adapters.persistence.models import ConversationMessageRecord
from app.interaction.adapters.persistence.models import SessionMemorySnapshotRecord
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
            return [
                {
                    "turn_id": record.turn_id,
                    "session_id": record.session_id,
                    "user_input": record.user_input,
                    "assistant_reply": record.assistant_reply,
                    "primary_topic": record.primary_topic,
                    "secondary_topics": list(record.secondary_topics or []),
                    "coherence_score": float(record.coherence_score),
                    "context_trace": dict(record.context_trace or {}),
                    "created_at": record.created_at.isoformat() if record.created_at else None,
                }
                for record in reversed(records)
            ]