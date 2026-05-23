from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.base_entity import BaseEntity


@dataclass
class SagaWorkflow(BaseEntity):
    title: str
    premise: str = ""
    summary: str = ""
    status: str = "active"
    world_building: str = ""
    command_history: list[str] = field(default_factory=list)
    act_history: list[dict[str, Any]] = field(default_factory=list)

    def record_command(self, command: str, note: str = "") -> None:
        normalized_command = command.strip()
        if not normalized_command:
            return

        timestamp = datetime.now(timezone.utc).isoformat()
        self.command_history.append(normalized_command)
        self.act_history.append(
            {
                "kind": "command",
                "index": len(self.command_history),
                "command": normalized_command,
                "note": note,
                "recorded_at": timestamp,
            }
        )
        self.touch()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "premise": self.premise,
            "summary": self.summary,
            "status": self.status,
            "world_building": self.world_building,
            "command_history": list(self.command_history),
            "act_history": list(self.act_history),
            "command_count": len(self.command_history),
            "act_count": len(self.act_history),
            "last_command": self.command_history[-1] if self.command_history else "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }