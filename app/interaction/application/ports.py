from __future__ import annotations

from typing import Protocol

from app.interaction.domain import ConversationMessage


class InteractionMessageRepositoryPort(Protocol):
    def save(self, message: ConversationMessage) -> ConversationMessage: ...

    def list_recent(self, limit: int = 20) -> list[ConversationMessage]: ...

    def count(self) -> int: ...

    def channel_counts(self) -> dict[str, int]: ...

    def get_session_memory(self, session_id: str) -> dict[str, object] | None: ...

    def save_session_memory(
        self,
        session_id: str,
        *,
        summary_text: str,
        sliding_window_size: int,
        last_turn_id: str | None,
        coherence_score: float,
    ) -> dict[str, object]: ...

    def get_session_topic_graph(self, session_id: str) -> dict[str, object] | None: ...

    def save_session_topic_graph(
        self,
        session_id: str,
        *,
        primary_topic: str,
        secondary_topics: list[str],
        topic_states: dict[str, str],
        edges: list[dict[str, object]],
    ) -> dict[str, object]: ...

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
    ) -> dict[str, object]: ...

    def list_turn_metrics(self, session_id: str, limit: int = 20) -> list[dict[str, object]]: ...

    def get_session_conditions(self, session_id: str) -> dict[str, object] | None: ...

    def save_session_conditions(self, session_id: str, *, world_rules: str) -> dict[str, object]: ...