from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, FastAPI, Request

from app.core.database import DatabaseManager
from app.core.events import EventBus
from app.core.settings import AppSettings


@dataclass
class AppContext:
    settings: AppSettings
    event_bus: EventBus
    database: DatabaseManager
    services: dict[str, Any] = field(default_factory=dict)
    module_groups: dict[str, tuple[str, ...]] = field(default_factory=dict)
    module_routers: dict[str, tuple[APIRouter, ...]] = field(default_factory=dict)


def get_app_context_from_app(app: FastAPI) -> AppContext:
    context = getattr(app.state, "context", None)
    if not isinstance(context, AppContext):
        raise RuntimeError("Application context not initialized")
    return context


def get_app_context_from_request(request: Request) -> AppContext:
    return get_app_context_from_app(request.app)