from __future__ import annotations

from typing import Any, Sequence

from fastapi import APIRouter, FastAPI

from app.core.app_context import get_app_context_from_app


def register_module_group(
    app: FastAPI,
    group_name: str,
    module_names: Sequence[str],
    *,
    routers: Sequence[APIRouter] = (),
) -> None:
    context = get_app_context_from_app(app)
    context.module_groups[group_name] = tuple(module_names)
    context.module_routers[group_name] = tuple(routers)


def register_service(app: FastAPI, service_name: str, service: Any) -> None:
    context = get_app_context_from_app(app)
    context.services[service_name] = service


def include_registered_routers(app: FastAPI) -> None:
    context = get_app_context_from_app(app)
    for group_name in context.module_groups:
        for router in context.module_routers.get(group_name, ()):
            app.include_router(router)