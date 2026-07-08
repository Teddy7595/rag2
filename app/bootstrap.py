from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from app.core.app_context import AppContext
from app.core.database import build_database_manager
from app.core.events import EventBus, init_event_bus
from app.core.module_registry import include_registered_routers
from app.core.settings import ensure_runtime_directories, load_settings
from app.adapters.web.web_module import register_web_module
from app.knowledge.knowledge_module import register_knowledge_module
from app.interaction.interaction_module import register_interaction_module
from app.models.models_module import register_models_module
from app.operations.operations_module import register_operations_module
from app.core.middleware import RequestContextMiddleware
from app.platform.platform_module import register_platform_module
from app.storage.storage_module import register_storage_module
from app.core.module_registry import dump_registered_routes


def create_app() -> FastAPI:
    # RAG2_PROJECT_ROOT lets tests redirect settings resolution (models dir
    # fallback scan, etc.) to an isolated tmp_path instead of the real repo,
    # which otherwise stays hardcoded to this file's on-disk location.
    project_root = Path(os.getenv("RAG2_PROJECT_ROOT") or Path(__file__).resolve().parents[1])
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

    app.add_middleware(RequestContextMiddleware)

    register_platform_module(app)
    register_storage_module(app)
    register_models_module(app)
    register_web_module(app)
    register_knowledge_module(app)
    from app.workshop.workshop_module import register_workshop_module
    register_workshop_module(app)
    register_interaction_module(app)
    register_operations_module(app)

    if database.settings.create_schema_on_start:
        database.create_schema()

    include_registered_routers(app)
    dump_registered_routes(app)
    return app