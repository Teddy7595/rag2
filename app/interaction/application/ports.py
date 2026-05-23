from __future__ import annotations

from typing import Protocol

from app.interaction.domain import ConversationMessage


class InteractionMessageRepositoryPort(Protocol):
    def save(self, message: ConversationMessage) -> ConversationMessage: ...

    def list_recent(self, limit: int = 20) -> list[ConversationMessage]: ...

    def count(self) -> int: ...

    def channel_counts(self) -> dict[str, int]: ...