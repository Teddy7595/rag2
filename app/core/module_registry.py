from __future__ import annotations

from typing import Any, Sequence

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from starlette.routing import Mount
from starlette.routing import WebSocketRoute

from app.core.app_context import get_app_context_from_app

_IGNORED_ROUTE_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _route_kind(route: object) -> str:
    if isinstance(route, APIRoute):
        return "http"
    if isinstance(route, WebSocketRoute):
        return "websocket"
    if isinstance(route, Mount):
        return "mount"
    return "other"


def _route_methods(route: object) -> tuple[str, ...]:
    if isinstance(route, APIRoute):
        methods = tuple(sorted(method for method in (route.methods or set()) if method not in {"HEAD", "OPTIONS"}))
        return methods or ("GET",)
    if isinstance(route, WebSocketRoute):
        return ("WS",)
    if isinstance(route, Mount):
        return ("MOUNT",)
    return ()


def _route_signature(route: object) -> tuple[str, str, tuple[str, ...], str]:
    return (
        _route_kind(route),
        getattr(route, "path", ""),
        _route_methods(route),
        getattr(route, "name", ""),
    )


def _route_target(route: object) -> str:
    if isinstance(route, APIRoute):
        endpoint = getattr(route, "endpoint", None)
        return getattr(endpoint, "__name__", getattr(route, "name", "")) or "handler"
    if isinstance(route, WebSocketRoute):
        return getattr(route, "name", "") or "websocket"
    if isinstance(route, Mount):
        return getattr(getattr(route, "app", None), "__class__", type(route.app)).__name__
    return getattr(route, "name", "") or "unknown"


def _format_route_line(route: object) -> str:
    methods = " ".join(_route_methods(route))
    path = getattr(route, "path", "")
    target = _route_target(route)
    return f"  {methods:<8} {path} -> {target}"


def dump_registered_routes(app: FastAPI) -> None:
    context = get_app_context_from_app(app)
    route_group_lookup: dict[tuple[str, str, tuple[str, ...], str], str] = {}
    for group_name, routers in context.module_routers.items():
        for router in routers:
            for route in router.routes:
                if _route_kind(route) == "other" or getattr(route, "path", "") in _IGNORED_ROUTE_PATHS:
                    continue
                route_group_lookup[_route_signature(route)] = group_name

    grouped_routes: dict[str, list[object]] = {group_name: [] for group_name in context.module_groups}
    grouped_routes["runtime"] = []

    for route in app.routes:
        if _route_kind(route) == "other" or getattr(route, "path", "") in _IGNORED_ROUTE_PATHS:
            continue
        group_name = route_group_lookup.get(_route_signature(route), "runtime")
        grouped_routes.setdefault(group_name, []).append(route)

    lines = ["Registered routes:"]
    for group_name in list(context.module_groups) + ["runtime"]:
        routes = grouped_routes.get(group_name, [])
        if not routes:
            continue
        label = "runtime" if group_name == "runtime" else group_name
        lines.append(f"- {label} ({len(routes)})")
        for route in sorted(routes, key=lambda item: (getattr(item, "path", ""), " ".join(_route_methods(item)), _route_target(item))):
            lines.append(_format_route_line(route))

    print("\n".join(lines), flush=True)


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