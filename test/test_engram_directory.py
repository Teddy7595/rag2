from __future__ import annotations

from app.knowledge.application.engram_directory import EngramDirectory
from app.knowledge.domain import Identity


def test_replace_preserves_active_identity_after_update() -> None:
    directory = EngramDirectory()
    identity = Identity(id="engram-1", name="Atlas")

    directory.cache(identity)
    directory.last_active_identity_id = "engram-1"

    updated_identity = Identity(id="engram-1", name="Atlas", behavior_prompt="Responde con calma.")
    directory.replace(updated_identity)

    current = directory.current_identity()

    assert current.id == "engram-1"
    assert current.behavior_prompt == "Responde con calma."
    assert directory.last_active_identity_id == "engram-1"
