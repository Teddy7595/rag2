"""Module registration for the dedicated web views."""

from __future__ import annotations

from fastapi import FastAPI

from app.adapters.web.page_routes import router
from app.core.module_registry import register_module_group


def register_web_module(app: FastAPI) -> None:
    register_module_group(app, "web", ("web",), routers=(router,))
