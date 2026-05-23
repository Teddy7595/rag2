from fastapi import FastAPI

from app.core.module_registry import register_module_group, register_service
from app.platform.adapters import register_platform_event_handlers
from app.platform.adapters.api import router as platform_router
from app.platform.application import PlatformService


def register_platform_module(app: FastAPI) -> None:
    service = PlatformService()
    register_service(app, "platform", service)
    register_module_group(app, "platform", ("platform",), routers=(platform_router,))
    register_platform_event_handlers(app)