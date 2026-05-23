from __future__ import annotations

from typing import Protocol

from app.knowledge.domain import KnowledgeEntry


class KnowledgeRepositoryPort(Protocol):
    def save(self, entry: KnowledgeEntry) -> KnowledgeEntry: ...

    def list_recent(self, limit: int = 20) -> list[KnowledgeEntry]: ...

    def count(self) -> int: ...