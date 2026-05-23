"""Module registration for the dedicated web views."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.adapters.web.page_routes import router
from app.core.app_context import get_app_context_from_app
from app.core.module_registry import register_module_group


def register_web_module(app: FastAPI) -> None:
    context = get_app_context_from_app(app)
    app.mount(
        context.settings.web_frontend_mount_path,
        StaticFiles(directory=context.settings.web_frontend_dir, html=True, check_dir=False),
        name="web_frontend",
    )
    register_module_group(app, "web", ("web",), routers=(router,))
