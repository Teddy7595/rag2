from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from html import escape

from fastapi import APIRouter, Request
from fastapi.routing import APIRoute
from fastapi.responses import HTMLResponse
from starlette.routing import Mount
from starlette.routing import WebSocketRoute

from app.core.app_context import get_app_context_from_request
from app.storage.service import UploadStorage


router = APIRouter(tags=["storage"])


def _get_storage(request: Request) -> UploadStorage:
    context = get_app_context_from_request(request)
    service = context.services.get("storage")
    if not isinstance(service, UploadStorage):
        raise RuntimeError("Storage service not registered")
    return service


def _file_items(files: tuple[str, ...], mount_path: str) -> str:
    if not files:
        return '<li style="opacity: 0.75;">Sin archivos todavía.</li>'
    return "".join(
        (
            "<li style=\"margin-bottom: 8px;\">"
            f'<a href="{escape(mount_path.rstrip("/") + "/" + file_name)}" '
            'style="color: #7dd3fc; text-decoration: none;">'
            f"{escape(file_name)}"
            "</a></li>"
        )
        for file_name in files
    )


def _card(title: str, content_html: str, *, accent: str = "#38bdf8") -> str:
    return (
        '<article style="background: rgba(8, 15, 32, 0.82); border: 1px solid rgba(148, 163, 184, 0.18); '
        'border-radius: 20px; padding: 20px; box-shadow: 0 24px 72px rgba(2, 6, 23, 0.32); '
        'backdrop-filter: blur(18px);">'
        '<div style="display: flex; align-items: start; justify-content: space-between; gap: 16px;">'
        f'<h2 style="margin: 0; font-size: 1.1rem; color: {accent};">{escape(title)}</h2>'
        '</div>'
        f'<div style="margin-top: 14px; color: #cbd5e1; line-height: 1.65;">{content_html}</div>'
        "</article>"
    )


_IGNORED_ROUTE_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
_METHOD_ACCENTS = {
    "GET": "#10b981",
    "POST": "#60a5fa",
    "PUT": "#f59e0b",
    "PATCH": "#a78bfa",
    "DELETE": "#ef4444",
    "WS": "#f472b6",
    "MOUNT": "#94a3b8",
}


def _pill(text: str, accent: str, *, uppercase: bool = True) -> str:
    return (
        f'<span class="pill" style="--pill-accent: {accent}; '
        f'text-transform: {"uppercase" if uppercase else "none"};">'
        f"{escape(text)}"
        "</span>"
    )


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


def _route_entry(route: object) -> dict[str, object]:
    endpoint = getattr(route, "endpoint", None)
    endpoint_name = getattr(endpoint, "__name__", getattr(route, "name", ""))
    endpoint_module = getattr(endpoint, "__module__", "")
    methods = _route_methods(route)
    kind = _route_kind(route)
    search_terms = " ".join(
        str(part)
        for part in (
            kind,
            getattr(route, "path", ""),
            " ".join(methods),
            getattr(route, "name", ""),
            endpoint_name,
            endpoint_module,
        )
        if part
    )
    return {
        "kind": kind,
        "path": getattr(route, "path", ""),
        "methods": methods,
        "name": getattr(route, "name", ""),
        "endpoint": endpoint_name,
        "endpoint_module": endpoint_module,
        "search": search_terms.lower(),
    }


def _route_inventory(request: Request) -> dict[str, object]:
    context = get_app_context_from_request(request)
    route_group_lookup: dict[tuple[str, str, tuple[str, ...], str], str] = {}
    for group_name, routers in context.module_routers.items():
        for router in routers:
            for route in router.routes:
                if _route_kind(route) == "other" or getattr(route, "path", "") in _IGNORED_ROUTE_PATHS:
                    continue
                route_group_lookup[_route_signature(route)] = group_name

    sections: dict[str, dict[str, object]] = {
        group_name: {
            "name": group_name,
            "module_names": list(context.module_groups.get(group_name, ())),
            "routes": [],
        }
        for group_name in context.module_groups
    }
    sections["runtime"] = {"name": "runtime", "module_names": [], "routes": []}

    counts = Counter()
    for route in request.app.routes:
        if _route_kind(route) == "other" or getattr(route, "path", "") in _IGNORED_ROUTE_PATHS:
            continue
        entry = _route_entry(route)
        group_name = route_group_lookup.get(_route_signature(route), "runtime")
        sections.setdefault(
            group_name,
            {
                "name": group_name,
                "module_names": list(context.module_groups.get(group_name, ())),
                "routes": [],
            },
        )["routes"].append(entry)
        counts[str(entry["kind"])] += 1

    ordered_sections: list[dict[str, object]] = []
    for group_name in list(context.module_groups) + ["runtime"]:
        section = sections.get(group_name)
        if not section or not section["routes"]:
            continue
        section["routes"].sort(key=lambda entry: (str(entry["path"]), " ".join(entry["methods"]), str(entry["name"])))
        section["route_count"] = len(section["routes"])
        section["display_name"] = "Infra y mounts" if group_name == "runtime" else group_name
        ordered_sections.append(section)

    summary = {
        "module_count": len([section for section in ordered_sections if section["name"] != "runtime"]),
        "route_count": sum(len(section["routes"]) for section in ordered_sections),
        "http_count": counts.get("http", 0),
        "websocket_count": counts.get("websocket", 0),
        "mount_count": counts.get("mount", 0),
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summary,
        "sections": ordered_sections,
    }


def _render_route_row(route: dict[str, object]) -> str:
    method_badges = "".join(
        _pill(method, _METHOD_ACCENTS.get(method, "#38bdf8")) for method in tuple(route["methods"])
    )
    route_kind = str(route["kind"])
    route_name = str(route["name"]) or "sin nombre"
    endpoint_module = str(route["endpoint_module"]) or "sin módulo"
    return (
        '<article class="route-row" data-route-row '
        f'data-search="{escape(str(route["search"]), quote=True)}">'
        '<div class="route-top">'
        f'{_pill(route_kind.upper(), _METHOD_ACCENTS.get(route_kind.upper(), "#7dd3fc"))}'
        f'<code class="route-path">{escape(str(route["path"]))}</code>'
        '</div>'
        '<div class="route-meta">'
        f"{method_badges}"
        f'<span>{escape(route_name)}</span>'
        f'<span>{escape(endpoint_module)}</span>'
        '</div>'
        '</article>'
    )


def _render_route_section(section: dict[str, object]) -> str:
    module_names = tuple(str(name) for name in section["module_names"])
    module_badges = "".join(_pill(module_name, "#7dd3fc", uppercase=False) for module_name in module_names)
    if not module_badges:
        module_badges = _pill("runtime", "#94a3b8", uppercase=False)
    route_rows = "".join(_render_route_row(route) for route in section["routes"])
    return (
        '<details class="module-section" data-route-section open>'
        '<summary class="module-summary">'
        '<div class="module-summary-text">'
        f'<p class="module-kicker">{"Infra" if section["name"] == "runtime" else "Módulo"}</p>'
        f'<h2 class="module-title">{escape(str(section["display_name"]))}</h2>'
        f'<div class="module-tags">{module_badges}</div>'
        '</div>'
        f'<div class="module-count">{section["route_count"]} rutas</div>'
        '</summary>'
        f'<div class="route-list">{route_rows}</div>'
        '</details>'
    )


def _render_route_explorer_page(*, title: str, eyebrow: str, headline: str, description: str, inventory: dict[str, object]) -> str:
    summary = inventory["summary"]
    sections = inventory["sections"]
    section_html = "".join(_render_route_section(section) for section in sections)
    return (
        "<!doctype html><html lang=\"es\"><head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title>"
        "<style>"
        ":root { color-scheme: dark; }"
        "* { box-sizing: border-box; }"
        "body { margin: 0; min-height: 100vh; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; "
        "background: radial-gradient(circle at top left, rgba(56, 189, 248, 0.18), transparent 24%), "
        "radial-gradient(circle at top right, rgba(16, 185, 129, 0.14), transparent 22%), "
        "linear-gradient(140deg, #050816 0%, #0f172a 52%, #111827 100%); color: #e2e8f0; }"
        ".page-shell { max-width: 1320px; margin: 0 auto; padding: 48px 20px 72px; }"
        ".hero { display: grid; gap: 18px; margin-bottom: 24px; }"
        ".eyebrow { margin: 0; text-transform: uppercase; letter-spacing: 0.18em; font-size: 0.76rem; color: #7dd3fc; }"
        ".headline { margin: 0; font-size: clamp(2.4rem, 4vw, 4.8rem); line-height: 0.95; max-width: 12ch; }"
        ".description { margin: 0; max-width: 74ch; font-size: 1.02rem; color: #cbd5e1; line-height: 1.7; }"
        ".stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; }"
        ".stat { background: rgba(8, 15, 32, 0.78); border: 1px solid rgba(148, 163, 184, 0.18); border-radius: 18px; padding: 16px 18px; backdrop-filter: blur(18px); }"
        ".stat-label { display: block; color: #94a3b8; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px; }"
        ".stat-value { font-size: 1.9rem; font-weight: 700; color: #f8fafc; }"
        ".stat-copy { display: block; margin-top: 6px; color: #cbd5e1; font-size: 0.9rem; }"
        ".search-shell { margin: 24px 0 30px; background: rgba(8, 15, 32, 0.78); border: 1px solid rgba(148, 163, 184, 0.18); border-radius: 22px; padding: 18px; backdrop-filter: blur(18px); }"
        ".search-label { display: block; margin-bottom: 10px; color: #cbd5e1; font-size: 0.9rem; }"
        ".search-input { width: 100%; border: 1px solid rgba(148, 163, 184, 0.22); background: rgba(2, 6, 23, 0.6); color: #f8fafc; border-radius: 16px; padding: 14px 16px; font-size: 0.98rem; outline: none; }"
        ".search-input:focus { border-color: rgba(125, 211, 252, 0.75); box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.16); }"
        ".section-list { display: grid; gap: 18px; }"
        ".module-section { background: rgba(8, 15, 32, 0.82); border: 1px solid rgba(148, 163, 184, 0.18); border-radius: 22px; padding: 18px; box-shadow: 0 24px 72px rgba(2, 6, 23, 0.32); backdrop-filter: blur(18px); }"
        ".module-section summary { list-style: none; display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; cursor: pointer; }"
        ".module-section summary::-webkit-details-marker { display: none; }"
        ".module-summary-text { display: grid; gap: 8px; }"
        ".module-kicker { margin: 0; color: #7dd3fc; text-transform: uppercase; letter-spacing: 0.16em; font-size: 0.72rem; }"
        ".module-title { margin: 0; font-size: 1.12rem; color: #f8fafc; }"
        ".module-tags { display: flex; flex-wrap: wrap; gap: 8px; }"
        ".module-count { padding: 10px 14px; border-radius: 999px; background: rgba(56, 189, 248, 0.08); color: #7dd3fc; border: 1px solid rgba(125, 211, 252, 0.18); font-size: 0.86rem; font-weight: 700; }"
        ".route-list { margin-top: 16px; display: grid; gap: 12px; }"
        ".route-row { border: 1px solid rgba(148, 163, 184, 0.14); background: rgba(2, 6, 23, 0.48); border-radius: 18px; padding: 14px 16px; }"
        ".route-top { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-bottom: 10px; }"
        ".route-path { margin: 0; color: #f8fafc; font-size: 0.98rem; word-break: break-word; }"
        ".route-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; color: #cbd5e1; font-size: 0.84rem; }"
        ".pill { display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; border-radius: 999px; border: 1px solid var(--pill-accent); color: var(--pill-accent); background: rgba(255, 255, 255, 0.04); font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; }"
        ".empty-state { margin-top: 18px; color: #cbd5e1; }"
        ".footnote { margin: 20px 2px 0; color: #94a3b8; font-size: 0.84rem; }"
        "</style>"
        "</head>"
        "<body>"
        '<main class="page-shell">'
        '<section class="hero">'
        f'<p class="eyebrow">{escape(eyebrow)}</p>'
        f'<h1 class="headline">{escape(headline)}</h1>'
        f'<p class="description">{escape(description)}</p>'
        '</section>'
        '<section class="stats">'
        f'<article class="stat"><span class="stat-label">Módulos</span><strong class="stat-value">{summary["module_count"]}</strong><span class="stat-copy">grupos registrados</span></article>'
        f'<article class="stat"><span class="stat-label">Rutas</span><strong class="stat-value" id="visible-route-count">{summary["route_count"]}</strong><span class="stat-copy">HTTP, websocket y mounts</span></article>'
        f'<article class="stat"><span class="stat-label">HTTP</span><strong class="stat-value">{summary["http_count"]}</strong><span class="stat-copy">endpoints REST</span></article>'
        f'<article class="stat"><span class="stat-label">WebSocket</span><strong class="stat-value">{summary["websocket_count"]}</strong><span class="stat-copy">canales en tiempo real</span></article>'
        f'<article class="stat"><span class="stat-label">Mounts</span><strong class="stat-value">{summary["mount_count"]}</strong><span class="stat-copy">archivos estáticos y runtime</span></article>'
        '</section>'
        '<section class="search-shell">'
        '<label class="search-label" for="route-filter">Filtrar por módulo, ruta, método o endpoint</label>'
        '<input id="route-filter" class="search-input" type="search" placeholder="Ej. /api/operations, GET, websocket, storage" autocomplete="off">'
        '</section>'
        '<section class="section-list">'
        f"{section_html}"
        '</section>'
        '<p id="route-empty-state" class="empty-state" hidden>No hay rutas que coincidan con ese filtro.</p>'
        f'<p class="footnote">Inventario generado en {escape(str(inventory["generated_at"]))} UTC.</p>'
        '</main>'
        '<script>'
        '(() => {'
        'const input = document.getElementById("route-filter");'
        'const sections = Array.from(document.querySelectorAll("[data-route-section]"));'
        'const visibleCount = document.getElementById("visible-route-count");'
        'const emptyState = document.getElementById("route-empty-state");'
        'const normalize = (value) => value.trim().toLowerCase();'
        'const update = () => {'
        '  const query = normalize(input.value);'
        '  let visible = 0;'
        '  sections.forEach((section) => {'
        '    let sectionVisible = false;'
        '    section.querySelectorAll("[data-route-row]").forEach((row) => {'
        '      const match = !query || row.dataset.search.includes(query);'
        '      row.hidden = !match;'
        '      if (match) {'
        '        visible += 1;'
        '        sectionVisible = true;'
        '      }'
        '    });'
        '    section.hidden = !sectionVisible;'
        '    if (query && sectionVisible) {'
        '      section.open = true;'
        '    }'
        '  });'
        '  visibleCount.textContent = String(visible);'
        '  emptyState.hidden = visible !== 0;'
        '};'
        'input.addEventListener("input", update);'
        'update();'
        '})();'
        '</script>'
        '</body></html>'
    )


def _render_page(*, title: str, eyebrow: str, headline: str, description: str, cards: list[str]) -> str:
    return (
        "<!doctype html><html lang=\"es\"><head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title>"
        "</head>"
        '<body style="margin: 0; min-height: 100vh; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; '
        'background: radial-gradient(circle at top left, rgba(56, 189, 248, 0.18), transparent 28%), '
        'radial-gradient(circle at top right, rgba(16, 185, 129, 0.14), transparent 24%), '
        'linear-gradient(140deg, #050816 0%, #0f172a 52%, #111827 100%); color: #e2e8f0;">'
        '<main style="max-width: 1120px; margin: 0 auto; padding: 48px 20px 72px;">'
        '<section style="display: grid; gap: 16px; margin-bottom: 28px;">'
        f'<p style="margin: 0; text-transform: uppercase; letter-spacing: 0.18em; font-size: 0.76rem; color: #7dd3fc;">{escape(eyebrow)}</p>'
        f'<h1 style="margin: 0; font-size: clamp(2.4rem, 4vw, 4.8rem); line-height: 0.95; max-width: 12ch;">{escape(headline)}</h1>'
        f'<p style="margin: 0; max-width: 72ch; font-size: 1.02rem; color: #cbd5e1;">{escape(description)}</p>'
        '</section>'
        '<section style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 18px;">'
        + "".join(cards)
        + "</section></main></body></html>"
    )


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request) -> HTMLResponse:
    context = get_app_context_from_request(request)
    storage = _get_storage(request)
    overview = storage.overview()

    cards = [
        _card(
            "Panel de almacenamiento",
            (
                f"<p style='margin-top: 0;'>Directorio base: <strong>{escape(overview['vault_dir'])}</strong></p>"
                f"<p>Montajes públicos: <a href='{escape(str(overview['public_mount']))}' style='color: #7dd3fc;'>"
                f"{escape(str(overview['public_mount']))}</a> y <a href='{escape(str(overview['uploads_mount']))}' style='color: #7dd3fc;'>"
                f"{escape(str(overview['uploads_mount']))}</a>.</p>"
            ),
        ),
        _card(
            "Accesos rápidos",
            (
                "<ul style='margin: 0; padding-left: 18px;'>"
                "<li><a href='/api/platform/health' style='color: #7dd3fc;'>/api/platform/health</a></li>"
                "<li><a href='/api/storage/overview' style='color: #7dd3fc;'>/api/storage/overview</a></li>"
                "<li><a href='/admin/models' style='color: #7dd3fc;'>/admin/models</a></li>"
                "<li><a href='/admin' style='color: #7dd3fc;'>/admin</a></li>"
                "</ul>"
            ),
            accent="#86efac",
        ),
        _card(
            f"Archivos públicos ({overview['public_file_count']})",
            f"<ul style='margin: 0; padding-left: 18px;'>{_file_items(tuple(overview['public_files']), '/public')}</ul>",
            accent="#fbbf24",
        ),
        _card(
            f"Uploads locales ({overview['upload_file_count']})",
            f"<ul style='margin: 0; padding-left: 18px;'>{_file_items(tuple(overview['upload_files']), '/uploads')}</ul>",
            accent="#f472b6",
        ),
    ]

    return HTMLResponse(
        _render_page(
            title=f"{context.settings.app_name} | Centro de control",
            eyebrow="RAG2 modular monolith",
            headline="Centro de control",
            description="Una vista ligera para navegar el runtime, el almacenamiento y los accesos principales del sistema.",
            cards=cards,
        )
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request) -> HTMLResponse:
    context = get_app_context_from_request(request)
    storage = _get_storage(request)
    overview = storage.overview()
    route_inventory = _route_inventory(request)
    route_summary = route_inventory["summary"]
    client_host = getattr(request.state, "client_host", "desconocido")
    is_local_request = getattr(request.state, "is_local_request", False)

    cards = [
        _card(
            "Seguridad local",
            (
                f"<p style='margin-top: 0;'>Cliente detectado: <strong>{escape(str(client_host))}</strong></p>"
                f"<p>Acceso local: <strong>{'sí' if is_local_request else 'no'}</strong></p>"
                f"<p>Restricción activa: <strong>{'sí' if context.settings.admin_local_only else 'no'}</strong></p>"
                f"<p>Rate limit: <strong>{context.settings.rate_limit_max_requests}</strong> solicitudes cada "
                f"<strong>{context.settings.rate_limit_window_seconds}</strong>s</p>"
                f"<p>Ban list: <strong>{escape(', '.join(context.settings.ban_list) or 'vacía')}</strong></p>"
            ),
            accent="#86efac",
        ),
        _card(
            "Modelos AI",
            (
                "<p style='margin-top: 0;'>Explora los bundles locales de <code>ai_models</code> y cambia entre texto/visión.</p>"
                "<p><a href='/admin/models' style='color: #7dd3fc;'>Abrir catálogo de modelos</a></p>"
            ),
            accent="#f59e0b",
        ),
        _card(
            "Visualizador de rutas",
            (
                f"<p style='margin-top: 0;'>Módulos registrados: <strong>{route_summary['module_count']}</strong></p>"
                f"<p>Rutas activas: <strong>{route_summary['route_count']}</strong> "
                f"(<strong>{route_summary['http_count']}</strong> HTTP, <strong>{route_summary['websocket_count']}</strong> WS, "
                f"<strong>{route_summary['mount_count']}</strong> mounts)</p>"
                "<p>Explora el árbol de módulos y rutas con una vista tipo NestJS.</p>"
                "<p><a href='/admin/routes' style='color: #7dd3fc;'>Abrir visualizador</a></p>"
            ),
            accent="#7dd3fc",
        ),
        _card(
            "Montajes y directorios",
            (
                f"<p style='margin-top: 0;'>Public: <code>{escape(overview['public_dir'])}</code></p>"
                f"<p>Uploads: <code>{escape(overview['uploads_dir'])}</code></p>"
                f"<p>Montajes: <a href='{escape(str(overview['public_mount']))}' style='color: #7dd3fc;'>"
                f"{escape(str(overview['public_mount']))}</a> y <a href='{escape(str(overview['uploads_mount']))}' style='color: #7dd3fc;'>"
                f"{escape(str(overview['uploads_mount']))}</a>.</p>"
            ),
            accent="#7dd3fc",
        ),
        _card(
            f"Inventario público ({overview['public_file_count']})",
            f"<ul style='margin: 0; padding-left: 18px;'>{_file_items(tuple(overview['public_files']), '/public')}</ul>",
            accent="#fbbf24",
        ),
        _card(
            f"Inventario uploads ({overview['upload_file_count']})",
            f"<ul style='margin: 0; padding-left: 18px;'>{_file_items(tuple(overview['upload_files']), '/uploads')}</ul>",
            accent="#f472b6",
        ),
    ]

    return HTMLResponse(
        _render_page(
            title=f"{context.settings.app_name} | Panel de administración",
            eyebrow="Panel interno",
            headline="Panel de administración",
            description="Acceso local a los directorios runtime, los montajes estáticos y los atajos operativos.",
            cards=cards,
        )
    )


@router.get("/admin/routes", response_class=HTMLResponse)
async def route_visualizer_page(request: Request) -> HTMLResponse:
    context = get_app_context_from_request(request)
    inventory = _route_inventory(request)
    return HTMLResponse(
        _render_route_explorer_page(
            title=f"{context.settings.app_name} | Visualizador de rutas",
            eyebrow="Explorador interno",
            headline="Visualizador de rutas",
            description="Mapa de los módulos y rutas registradas, agrupado como un árbol de navegación estilo NestJS.",
            inventory=inventory,
        )
    )


@router.get("/api/storage/overview")
async def storage_overview(request: Request) -> dict[str, object]:
    return _get_storage(request).overview()


@router.get("/api/storage/public")
async def list_public_files(request: Request) -> list[str]:
    return list(_get_storage(request).list_public_files())


@router.get("/api/storage/uploads")
async def list_upload_files(request: Request) -> list[str]:
    return list(_get_storage(request).list_upload_files())