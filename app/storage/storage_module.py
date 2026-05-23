from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.app_context import get_app_context_from_app
from app.core.module_registry import register_module_group, register_service
from app.storage.routes import router as storage_router
from app.storage.service import UploadStorage


def register_storage_module(app: FastAPI) -> None:
    context = get_app_context_from_app(app)
    service = UploadStorage(context.settings)
    register_service(app, "storage", service)
    register_module_group(app, "storage", ("storage",), routers=(storage_router,))
    app.mount("/public", StaticFiles(directory=service.public_dir), name="public")
    app.mount("/uploads", StaticFiles(directory=service.uploads_dir), name="uploads")