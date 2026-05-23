from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from app.core.app_context import AppContext
from app.core.database import build_database_manager
from app.core.events import EventBus, init_event_bus
from app.core.module_registry import include_registered_routers
from app.core.settings import ensure_runtime_directories, load_settings
from app.knowledge.knowledge_module import register_knowledge_module
from app.interaction.interaction_module import register_interaction_module
from app.operations.operations_module import register_operations_module
from app.platform.platform_module import register_platform_module


def create_app() -> FastAPI:
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")

    settings = load_settings(project_root)
    ensure_runtime_directories(settings)
    database = build_database_manager(settings)

    event_bus = EventBus()
    init_event_bus(event_bus)

    app = FastAPI(
        title=settings.app_name,
        description=settings.app_description,
        version=settings.app_version,
        debug=settings.debug,
    )
    context = AppContext(settings=settings, event_bus=event_bus, database=database)
    app.state.context = context
    app.state.settings = settings
    app.state.event_bus = event_bus
    app.state.database = database
    app.state.services = context.services
    app.state.module_groups = context.module_groups
    app.state.module_routers = context.module_routers

    register_platform_module(app)
    register_knowledge_module(app)
    register_interaction_module(app)
    register_operations_module(app)

    if database.settings.create_schema_on_start:
        database.create_schema()

    include_registered_routers(app)
    return app