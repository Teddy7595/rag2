from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute
from fastapi.templating import Jinja2Templates
from starlette.routing import Mount, WebSocketRoute

from app.core.app_context import get_app_context_from_request
from app.models.service import ModelCatalogService
from app.storage.service import UploadStorage

router = APIRouter(tags=["web"])
TEMPLATES_DIR = Path(__file__).with_name("templates")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
_IGNORED_ROUTE_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _base_context(request: Request) -> dict[str, Any]:
    context = get_app_context_from_request(request)
    settings = context.settings
    frontend = {
        "mount_path": settings.web_frontend_mount_path,
        "dir": str(settings.web_frontend_dir),
        "root_tag": settings.web_frontend_root_tag,
        "root_id": settings.web_frontend_root_id,
        "script_type": settings.web_frontend_script_type,
        "styles": settings.web_frontend_styles,
        "scripts": settings.web_frontend_scripts,
    }
    frontend["has_assets"] = bool(frontend["styles"] or frontend["scripts"])
    return {
        "app_name": settings.app_name,
        "app_description": settings.app_description,
        "app_version": settings.app_version,
        "frontend": frontend,
    }


def _page_context(
    request: Request,
    *,
    title: str,
    eyebrow: str,
    headline: str,
    description: str,
    **extra: Any,
) -> dict[str, Any]:
    context = _base_context(request)
    context.update(
        {
            "title": title,
            "eyebrow": eyebrow,
            "headline": headline,
            "description": description,
        }
    )
    context.update(extra)
    context["request"] = request
    return context


def _render(request: Request, template_name: str, **context: Any) -> HTMLResponse:
    return templates.TemplateResponse(request, template_name, _page_context(request, **context))


def _get_storage(request: Request) -> UploadStorage:
    context = get_app_context_from_request(request)
    storage = context.services.get("storage")
    if not isinstance(storage, UploadStorage):
        raise RuntimeError("Storage service not available")
    return storage


def _get_model_service(request: Request) -> ModelCatalogService:
    context = get_app_context_from_request(request)
    service = context.services.get("models")
    if not isinstance(service, ModelCatalogService):
        raise RuntimeError("Model catalog service not available")
    return service


def _is_route_object(route: object) -> bool:
    return isinstance(route, (APIRoute, WebSocketRoute, Mount))


def _route_kind(route: object) -> str:
    if isinstance(route, APIRoute):
        return "http"
    if isinstance(route, WebSocketRoute):
        return "websocket"
    if isinstance(route, Mount):
        return "mount"
    return type(route).__name__.lower()


def _route_methods(route: object) -> tuple[str, ...]:
    if isinstance(route, APIRoute):
        methods = tuple(sorted(method for method in (route.methods or set()) if method not in {"HEAD", "OPTIONS"}))
        return methods or ("GET",)
    if isinstance(route, WebSocketRoute):
        return ("WS",)
    if isinstance(route, Mount):
        return ("MOUNT",)
    return tuple()


def _route_signature(route: object) -> tuple[str, str, tuple[str, ...], str]:
    return (
        _route_kind(route),
        str(getattr(route, "path", getattr(route, "path_format", ""))),
        _route_methods(route),
        str(getattr(route, "name", "")),
    )


def _route_should_skip(route: object) -> bool:
    return str(getattr(route, "path", "")) in _IGNORED_ROUTE_PATHS


def _route_entry(route: object, group_name: str) -> dict[str, Any]:
    methods = _route_methods(route)
    path = str(getattr(route, "path", getattr(route, "path_format", "")))
    name = str(getattr(route, "name", ""))
    kind = _route_kind(route)
    return {
        "kind": kind,
        "path": path,
        "methods": methods,
        "name": name,
        "module": group_name,
        "search": " ".join([group_name, path, " ".join(methods), name, kind]).lower(),
    }


def _route_inventory(request: Request) -> dict[str, Any]:
    context = get_app_context_from_request(request)
    route_group_lookup: dict[tuple[str, str, tuple[str, ...], str], str] = {}
    for group_name, routers in context.module_routers.items():
        for router in routers:
            for route in router.routes:
                if not _is_route_object(route) or _route_should_skip(route):
                    continue
                route_group_lookup[_route_signature(route)] = group_name

    grouped_routes: dict[str, list[dict[str, Any]]] = {}
    http_count = 0
    websocket_count = 0
    mount_count = 0

    for route in request.app.routes:
        if not _is_route_object(route) or _route_should_skip(route):
            continue
        group_name = route_group_lookup.get(_route_signature(route), "runtime")
        entry = _route_entry(route, group_name)
        grouped_routes.setdefault(group_name, []).append(entry)
        if entry["kind"] == "http":
            http_count += 1
        elif entry["kind"] == "websocket":
            websocket_count += 1
        elif entry["kind"] == "mount":
            mount_count += 1

    sections: list[dict[str, Any]] = []
    for group_name in list(context.module_groups) + ["runtime"]:
        routes = grouped_routes.get(group_name)
        if not routes:
            continue
        sections.append(
            {
                "name": group_name,
                "display_name": group_name.replace("_", " ").title(),
                "module_names": context.module_groups.get(group_name, tuple()),
                "routes": routes,
                "route_count": len(routes),
            }
        )

    total_routes = sum(len(routes) for routes in grouped_routes.values())
    return {
        "summary": {
            "group_count": len(sections),
            "route_count": total_routes,
            "http_count": http_count,
            "websocket_count": websocket_count,
            "mount_count": mount_count,
        },
        "sections": sections,
        "generated_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }


def _model_catalog_context(request: Request) -> dict[str, Any]:
    service = _get_model_service(request)
    catalog = cast(dict[str, Any], service.catalog())
    return {"catalog": catalog}


def _runtime_context(request: Request) -> dict[str, Any]:
    catalog_context = _model_catalog_context(request)
    return {"runtime": catalog_context["catalog"]["runtime"], "catalog": catalog_context["catalog"]}


@router.get("/")
async def landing_page(request: Request) -> HTMLResponse:
    storage = _get_storage(request)
    overview = storage.overview()
    return _render(
        request,
        "home.html",
        title=f"{_base_context(request)['app_name']} | Centro de control",
        eyebrow="Vista general",
        headline="Centro de control",
        description="Navega el almacenamiento, las herramientas administrativas y los módulos locales desde un único punto de entrada.",
        overview=overview,
    )


@router.get("/admin")
async def admin_page(request: Request) -> HTMLResponse:
    context = get_app_context_from_request(request)
    storage = _get_storage(request)
    overview = storage.overview()
    catalog_context = _model_catalog_context(request)
    return _render(
        request,
        "admin.html",
        title=f"{context.settings.app_name} | Panel de administración",
        eyebrow="Administración",
        headline="Panel de administración",
        description="Concentra las funciones operativas del sistema en una sola vista.",
        overview=overview,
        module_count=len(context.module_groups),
        runtime=catalog_context["catalog"]["runtime"],
    )


@router.get("/chat")
async def chat_page(request: Request) -> HTMLResponse:
    context = get_app_context_from_request(request)
    catalog_context = _model_catalog_context(request)
    return _render(
        request,
        "chat.html",
        title=f"{context.settings.app_name} | Chat realtime",
        eyebrow="Realtime chat",
        headline="Chat realtime",
        description="Interfaz mobile-first conectada al websocket del modulo interaction, lista para enchufar el motor local cuando el runtime de inferencia quede cableado.",
        runtime=catalog_context["catalog"]["runtime"],
    )


@router.get("/admin/runtime-ai")
async def runtime_ai_page(request: Request) -> HTMLResponse:
    context = get_app_context_from_request(request)
    runtime_context = _runtime_context(request)
    return _render(
        request,
        "runtime_ai.html",
        title=f"{context.settings.app_name} | Runtime AI",
        eyebrow="Runtime AI",
        headline="Diagnostico de inferencia local",
        description="Inspecciona el binding de llama.cpp, verifica la seleccion local activa y ejecuta smoke tests de texto y vision desde el portal admin.",
        **runtime_context,
    )


@router.get("/admin/context-graph")
async def context_graph_page(request: Request) -> HTMLResponse:
    context = get_app_context_from_request(request)
    runtime_context = _runtime_context(request)
    return _render(
        request,
        "context_graph.html",
        title=f"{context.settings.app_name} | Context Graph",
        eyebrow="Context Graph",
        headline="Laboratorio de coherencia",
        description=(
            "Construye el grafo de contexto del RAG, analiza tema principal/secundarios y "
            "debate elementos de saga para generar memoria inspiracional reutilizable por engrama."
        ),
        **runtime_context,
    )


@router.get("/admin/session-intel")
async def session_intel_page(request: Request) -> HTMLResponse:
    context = get_app_context_from_request(request)
    runtime_context = _runtime_context(request)
    return _render(
        request,
        "session_intel.html",
        title=f"{context.settings.app_name} | Session Intelligence",
        eyebrow="Session Intelligence",
        headline="Monitor de continuidad por sesion",
        description=(
            "Inspecciona memoria incremental, grafo de temas y metricas de coherencia por turno "
            "desde una sola vista de observabilidad operativa."
        ),
        **runtime_context,
    )


@router.get("/ui")
async def frontend_shell_page(request: Request) -> HTMLResponse:
    context = get_app_context_from_request(request)
    return _render(
        request,
        "frontend.html",
        title=f"{context.settings.app_name} | Frontend shell",
        eyebrow="Frontend",
        headline="Shell de frontend",
        description="Usa esta vista para abrir un build compilado de Angular, Vite o vanilla o para apuntar a un frontend montado por static files.",
    )


@router.get("/admin/routes")
async def route_visualizer_page(request: Request) -> HTMLResponse:
    context = get_app_context_from_request(request)
    inventory = _route_inventory(request)
    return _render(
        request,
        "routes.html",
        title=f"{context.settings.app_name} | Visualizador de rutas",
        eyebrow="Mapa de rutas",
        headline="Visualizador de rutas",
        description="Revisa cómo se distribuyen las rutas por módulo, incluyendo las APIs, los mounts y los websockets.",
        inventory=inventory,
    )


@router.get("/admin/models")
async def models_admin_page(request: Request) -> HTMLResponse:
    context = get_app_context_from_request(request)
    catalog_context = _model_catalog_context(request)
    return _render(
        request,
        "models.html",
        title=f"{context.settings.app_name} | Catálogo de modelos",
        eyebrow="Catálogo AI",
        headline="Modelos y proveedores",
        description="Explora los bundles locales de ai_models, ve qué soporta texto o visión y cambia la selección activa sin tocar la consola.",
        **catalog_context,
    )
