from __future__ import annotations

from fastapi import FastAPI

from app.core.app_context import get_app_context_from_app
from app.core.module_registry import register_module_group, register_service
from app.models.routes import router as models_router
from app.models.service import ModelCatalogService


def register_models_module(app: FastAPI) -> None:
    context = get_app_context_from_app(app)
    service = ModelCatalogService(context.settings)
    register_service(app, "models", service)
    register_module_group(app, "models", ("models",), routers=(models_router,))