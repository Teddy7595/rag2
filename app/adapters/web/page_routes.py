from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from string import Template
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute
from starlette.routing import Mount, WebSocketRoute

from app.core.app_context import get_app_context_from_request
from app.models.service import ModelCatalogService
from app.storage.service import UploadStorage

router = APIRouter(tags=["web"])

_PAGE_TEMPLATE = Template(
    """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>$title</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #050816;
      --bg-soft: rgba(8, 15, 32, 0.82);
      --border: rgba(148, 163, 184, 0.18);
      --text: #e2e8f0;
      --muted: #cbd5e1;
      --soft: #94a3b8;
      --accent: #7dd3fc;
      --accent-strong: #38bdf8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(56, 189, 248, 0.18), transparent 24%),
        radial-gradient(circle at top right, rgba(16, 185, 129, 0.14), transparent 22%),
        linear-gradient(140deg, #050816 0%, #0f172a 52%, #111827 100%);
      color: var(--text);
    }
    a { color: inherit; }
    code {
      padding: 0.15rem 0.35rem;
      border-radius: 0.45rem;
      background: rgba(2, 6, 23, 0.6);
      color: #f8fafc;
    }
    .shell {
      max-width: 1320px;
      margin: 0 auto;
      padding: 48px 20px 72px;
    }
    .hero {
      display: grid;
      gap: 16px;
      margin-bottom: 24px;
    }
    .eyebrow {
      margin: 0;
      text-transform: uppercase;
      letter-spacing: 0.18em;
      font-size: 0.76rem;
      color: var(--accent);
    }
    .headline {
      margin: 0;
      font-size: clamp(2.4rem, 4vw, 4.8rem);
      line-height: 0.95;
      max-width: 14ch;
    }
    .description {
      margin: 0;
      max-width: 78ch;
      font-size: 1.02rem;
      color: var(--muted);
      line-height: 1.7;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 14px;
      margin-bottom: 18px;
    }
    .stat-card,
    .card,
    .route-section,
    .bundle-card,
    .control-card,
    .panel {
      background: var(--bg-soft);
      border: 1px solid var(--border);
      border-radius: 20px;
      box-shadow: 0 24px 72px rgba(2, 6, 23, 0.32);
      backdrop-filter: blur(18px);
    }
    .stat-card {
      padding: 16px 18px;
    }
    .stat-label,
    .card-label,
    .control-label {
      display: block;
      color: var(--soft);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 8px;
    }
    .stat-value {
      display: block;
      font-size: 1.9rem;
      font-weight: 700;
      color: #f8fafc;
    }
    .stat-copy,
    .note,
    .secondary-note {
      display: block;
      margin-top: 6px;
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.55;
    }
    .panel-grid,
    .control-grid,
    .bundle-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 18px;
    }
    .card,
    .bundle-card,
    .control-card,
    .panel {
      padding: 18px;
    }
    .card-title,
    .bundle-title,
    .control-title,
    .panel-title {
      margin: 0 0 10px;
      font-size: 1.08rem;
      color: #f8fafc;
    }
    .card-body,
    .panel-body {
      color: var(--muted);
      line-height: 1.65;
    }
    .card-actions,
    .action-row {
      margin-top: 14px;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .link-button,
    .save-button,
    .bundle-button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border-radius: 999px;
      border: 1px solid rgba(125, 211, 252, 0.22);
      background: rgba(56, 189, 248, 0.09);
      color: #e0f2fe;
      padding: 10px 14px;
      font-size: 0.92rem;
      font-weight: 700;
      text-decoration: none;
      cursor: pointer;
    }
    .save-button { margin-top: 14px; }
    .link-button:hover,
    .save-button:hover,
    .bundle-button:hover {
      border-color: rgba(125, 211, 252, 0.45);
      background: rgba(56, 189, 248, 0.16);
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 10px;
      border-radius: 999px;
      border: 1px solid var(--pill-accent);
      color: var(--pill-accent);
      background: rgba(255, 255, 255, 0.04);
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .pill[data-uppercase="false"] {
      text-transform: none;
      letter-spacing: 0;
    }
    .route-search {
      margin: 24px 0 30px;
      padding: 18px;
      border-radius: 22px;
      border: 1px solid var(--border);
      background: var(--bg-soft);
      backdrop-filter: blur(18px);
    }
    .search-label {
      display: block;
      margin-bottom: 10px;
      color: var(--muted);
      font-size: 0.92rem;
    }
    .search-input,
    .control-input,
    .control-select {
      width: 100%;
      border: 1px solid rgba(148, 163, 184, 0.22);
      background: rgba(2, 6, 23, 0.6);
      color: #f8fafc;
      border-radius: 16px;
      padding: 13px 14px;
      font-size: 0.98rem;
      outline: none;
    }
    .search-input:focus,
    .control-input:focus,
    .control-select:focus {
      border-color: rgba(125, 211, 252, 0.75);
      box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.16);
    }
    .route-list {
      display: grid;
      gap: 18px;
    }
    .route-section {
      padding: 18px;
    }
    .route-section summary {
      list-style: none;
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      cursor: pointer;
    }
    .route-section summary::-webkit-details-marker { display: none; }
    .route-summary {
      display: grid;
      gap: 8px;
    }
    .route-kicker {
      margin: 0;
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.16em;
      font-size: 0.72rem;
    }
    .route-module {
      margin: 0;
      font-size: 1.12rem;
      color: #f8fafc;
    }
    .route-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .route-count {
      padding: 10px 14px;
      border-radius: 999px;
      background: rgba(56, 189, 248, 0.08);
      color: var(--accent);
      border: 1px solid rgba(125, 211, 252, 0.18);
      font-size: 0.86rem;
      font-weight: 700;
      white-space: nowrap;
    }
    .route-rows {
      margin-top: 16px;
      display: grid;
      gap: 12px;
    }
    .route-row {
      border: 1px solid rgba(148, 163, 184, 0.14);
      background: rgba(2, 6, 23, 0.48);
      border-radius: 18px;
      padding: 14px 16px;
    }
    .route-path {
      margin: 0 0 8px;
      color: #f8fafc;
      font-size: 0.98rem;
      word-break: break-word;
    }
    .route-meta,
    .bundle-meta {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 0.84rem;
    }
    .empty-state {
      margin-top: 18px;
      color: var(--muted);
    }
    .control-row {
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }
    .bundle-list {
      display: grid;
      gap: 12px;
      margin-top: 12px;
    }
    .bundle-title-row {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: flex-start;
      margin-bottom: 8px;
    }
    .bundle-description {
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
    }
    .footnote {
      margin: 20px 2px 0;
      color: var(--soft);
      font-size: 0.84rem;
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <p class="eyebrow">$eyebrow</p>
      <h1 class="headline">$headline</h1>
      <p class="description">$description</p>
    </section>
    $body_html
  </main>
  $extra_js
</body>
</html>
"""
)


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


def _card(title: str, body_html: str, *, accent: str = "#7dd3fc") -> str:
    return (
        f'<article class="card" style="--pill-accent: {accent};">'
        f'<p class="card-label">{escape(title)}</p>'
        f'<div class="card-body">{body_html}</div>'
        '</article>'
    )


def _pill(text: str, accent: str, *, uppercase: bool = True) -> str:
    return (
        f'<span class="pill" data-uppercase="{str(uppercase).lower()}" style="--pill-accent: {accent};">'
        f'{escape(text)}'
        '</span>'
    )


def _select_option(value: str, label: str, *, selected: bool = False) -> str:
  selected_attr = " selected" if selected else ""
  return f'<option value="{escape(value, quote=True)}"{selected_attr}>{escape(label)}</option>'


def _page(*, title: str, eyebrow: str, headline: str, description: str, body_html: str, extra_js: str = "") -> str:
    return _PAGE_TEMPLATE.substitute(
        title=escape(title),
        eyebrow=escape(eyebrow),
        headline=escape(headline),
        description=escape(description),
        body_html=body_html,
        extra_js=extra_js,
    )


def _is_route_route(route: object) -> bool:
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
    methods = getattr(route, "methods", None)
    if not methods:
        return tuple()
    return tuple(sorted(str(method) for method in methods))


def _route_signature(route: object) -> tuple[str, str, tuple[str, ...], str]:
    return (
        _route_kind(route),
        str(getattr(route, "path", getattr(route, "path_format", ""))),
        _route_methods(route),
        str(getattr(route, "name", "")),
    )


def _should_skip_route(route: object) -> bool:
    path = str(getattr(route, "path", ""))
    return path in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _route_entry(route: object, group_name: str) -> dict[str, Any]:
    methods = _route_methods(route)
    path = str(getattr(route, "path", getattr(route, "path_format", "")))
    return {
        "kind": _route_kind(route),
        "path": path,
        "methods": methods,
        "name": str(getattr(route, "name", "")),
        "module": group_name,
        "search": " ".join(
            [group_name, path, " ".join(methods), str(getattr(route, "name", "")), _route_kind(route)]
        ).lower(),
    }


def _route_inventory(request: Request) -> dict[str, Any]:
    context = get_app_context_from_request(request)
    route_group_lookup: dict[tuple[str, str, tuple[str, ...], str], str] = {}
    for group_name, routers in context.module_routers.items():
        for router in routers:
            for route in router.routes:
                if not _is_route_route(route) or _should_skip_route(route):
                    continue
                route_group_lookup[_route_signature(route)] = group_name

    grouped_routes: dict[str, list[dict[str, object]]] = {}
    http_count = 0
    websocket_count = 0
    mount_count = 0

    for route in request.app.routes:
        if not _is_route_route(route) or _should_skip_route(route):
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

    sections: list[dict[str, object]] = []
    for group_name in list(context.module_groups) + ["runtime"]:
        routes = grouped_routes.get(group_name)
        if not routes:
            continue
        modules = context.module_groups.get(group_name, tuple())
        sections.append(
            {
                "name": group_name,
                "display_name": group_name.replace("_", " ").title(),
                "module_names": modules,
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


def _render_route_row(route: dict[str, Any]) -> str:
    methods = cast(tuple[str, ...], route["methods"])
    method_pills = "".join(_pill(str(method), "#f59e0b", uppercase=False) for method in methods) if methods else _pill("ANY", "#f59e0b", uppercase=False)
    return (
        f'<div class="route-row" data-route-row data-search="{escape(str(route["search"]))}">'
        f'<p class="route-path">{escape(str(route["path"]))}</p>'
        f'<div class="route-meta">{method_pills}{_pill(str(route["kind"]), "#7dd3fc", uppercase=False)}'
        f'<span>{escape(str(route["name"]))}</span>'
        f'<span>· {escape(str(route["module"]))}</span>'
        '</div>'
        '</div>'
    )


def _render_route_section(section: dict[str, Any]) -> str:
    module_names = tuple(str(name) for name in cast(tuple[str, ...], section["module_names"]))
    module_badges = "".join(_pill(module_name, "#7dd3fc", uppercase=False) for module_name in module_names)
    if not module_badges:
        module_badges = _pill("runtime", "#94a3b8", uppercase=False)
    route_rows = "".join(_render_route_row(route) for route in cast(list[dict[str, Any]], section["routes"]))
    return (
        '<details class="route-section" data-route-section open>'
        '<summary>'
        '<div class="route-summary">'
        f'<p class="route-kicker">{"Infra" if section["name"] == "runtime" else "Módulo"}</p>'
        f'<h2 class="route-module">{escape(str(section["display_name"]))}</h2>'
        f'<div class="route-tags">{module_badges}</div>'
        '</div>'
        f'<div class="route-count">{section["route_count"]} rutas</div>'
        '</summary>'
        f'<div class="route-rows">{route_rows}</div>'
        '</details>'
    )


def _render_route_inventory_page(request: Request, *, title: str, eyebrow: str, headline: str, description: str) -> HTMLResponse:
    inventory = _route_inventory(request)
    summary = cast(dict[str, int], inventory["summary"])
    sections = cast(list[dict[str, Any]], inventory["sections"])
    section_html = "".join(_render_route_section(section) for section in sections)
    body_html = (
        '<section class="stats">'
        f'<article class="stat-card"><span class="stat-label">Módulos</span><strong class="stat-value">{summary["group_count"]}</strong><span class="stat-copy">grupos registrados</span></article>'
        f'<article class="stat-card"><span class="stat-label">Rutas</span><strong class="stat-value" id="visible-route-count">{summary["route_count"]}</strong><span class="stat-copy">HTTP, websocket y mounts</span></article>'
        f'<article class="stat-card"><span class="stat-label">HTTP</span><strong class="stat-value">{summary["http_count"]}</strong><span class="stat-copy">endpoints REST</span></article>'
        f'<article class="stat-card"><span class="stat-label">WebSocket</span><strong class="stat-value">{summary["websocket_count"]}</strong><span class="stat-copy">canales en tiempo real</span></article>'
        f'<article class="stat-card"><span class="stat-label">Mounts</span><strong class="stat-value">{summary["mount_count"]}</strong><span class="stat-copy">archivos estáticos y runtime</span></article>'
        '</section>'
        '<section class="route-search">'
        '<label class="search-label" for="route-filter">Filtrar por módulo, ruta, método o endpoint</label>'
        '<input id="route-filter" class="search-input" type="search" placeholder="Ej. /api/operations/sagas, GET, websocket, storage" autocomplete="off">'
        '</section>'
        '<section class="route-list">'
        f"{section_html}"
        '</section>'
        '<p id="route-empty-state" class="empty-state" hidden>No hay rutas que coincidan con ese filtro.</p>'
        f'<p class="footnote">Inventario generado en {escape(str(inventory["generated_at"]))} UTC.</p>'
    )
    extra_js = """
<script>
(() => {
  const input = document.getElementById('route-filter');
  const sections = Array.from(document.querySelectorAll('[data-route-section]'));
  const visibleCount = document.getElementById('visible-route-count');
  const emptyState = document.getElementById('route-empty-state');
  const normalize = (value) => value.trim().toLowerCase();
  const update = () => {
    const query = normalize(input.value);
    let visible = 0;
    sections.forEach((section) => {
      let sectionVisible = false;
      section.querySelectorAll('[data-route-row]').forEach((row) => {
        const match = !query || row.dataset.search.includes(query);
        row.hidden = !match;
        if (match) {
          visible += 1;
          sectionVisible = true;
        }
      });
      section.hidden = !sectionVisible;
      if (query && sectionVisible) {
        section.open = true;
      }
    });
    visibleCount.textContent = String(visible);
    emptyState.hidden = visible !== 0;
  };
  input.addEventListener('input', update);
  update();
})();
</script>
"""
    return HTMLResponse(
        _page(
            title=title,
            eyebrow=eyebrow,
            headline=headline,
            description=description,
            body_html=body_html,
            extra_js=extra_js,
        )
    )


def _model_bundle_options(bundles: list[dict[str, object]], selected_bundle_id: str | None) -> str:
    options = ['<option value="">Sin bundle local</option>']
    for bundle in bundles:
        bundle_id = str(bundle["bundle_id"])
        label = f'{bundle_id} · {bundle["name"]}'
        if bundle.get("is_embedding_cache"):
            label += " · cache"
        elif bundle.get("supports_vision") and bundle.get("supports_text"):
            label += " · texto + visión"
        elif bundle.get("supports_vision"):
            label += " · visión"
        elif bundle.get("supports_text"):
            label += " · texto"
        selected = " selected" if selected_bundle_id == bundle_id else ""
        options.append(f'<option value="{escape(bundle_id, quote=True)}"{selected}>{escape(label)}</option>')
    return "".join(options)


def _bundle_card(bundle: dict[str, Any], *, text_selection: str | None, vision_selection: str | None) -> str:
    artifacts = cast(list[Any], bundle.get("artifacts", []))
    artifact_list = "".join(f'<li>{escape(str(artifact))}</li>' for artifact in artifacts) if artifacts else "<li>Sin archivos detectados</li>"
    actions: list[str] = []
    if bundle.get("supports_text") and not bundle.get("is_embedding_cache"):
        actions.append(
            f'<button type="button" class="bundle-button" data-select-text-bundle="{escape(str(bundle["bundle_id"]), quote=True)}">Usar para texto</button>'
        )
    if bundle.get("supports_vision") and not bundle.get("is_embedding_cache"):
        actions.append(
            f'<button type="button" class="bundle-button" data-select-vision-bundle="{escape(str(bundle["bundle_id"]), quote=True)}">Usar para visión</button>'
        )
    meta: list[str] = []
    if bundle.get("supports_text"):
        meta.append("texto")
    if bundle.get("supports_vision"):
        meta.append("visión")
    if bundle.get("is_embedding_cache"):
        meta.append("embedding cache")
    meta_html = " ".join(escape(item) for item in meta) or "sin capacidades"
    return (
        '<article class="bundle-card">'
        '<div class="bundle-title-row">'
        f'<h3 class="bundle-title">{escape(str(bundle["name"]))}</h3>'
        f'<span class="pill" style="--pill-accent: #86efac;">{escape(str(bundle["bundle_id"]))}</span>'
        '</div>'
        f'<p class="bundle-description">{escape(meta_html)}</p>'
        f'<div class="bundle-meta"><span>{escape(str(bundle["provider_hint"]))}</span><span>·</span><span>{escape(str(bundle["artifact_count"]))} archivos</span></div>'
        f'<ul>{artifact_list}</ul>'
        f'<div class="action-row">{"".join(actions)}</div>'
        '</article>'
    )


def _render_model_catalog_page(request: Request, *, title: str, eyebrow: str, headline: str, description: str) -> HTMLResponse:
    service = _get_model_service(request)
    catalog = cast(dict[str, Any], service.catalog())
    bundles = cast(list[dict[str, Any]], catalog["bundles"])
    selection = cast(dict[str, Any], catalog["selection"])
    resolved = cast(dict[str, Any], catalog["resolved"])
    providers = cast(dict[str, Any], catalog["providers"])

    text_bundles = [bundle for bundle in bundles if bundle["supports_text"] and not bundle["is_embedding_cache"]]
    vision_bundles = [bundle for bundle in bundles if bundle["supports_vision"] and not bundle["is_embedding_cache"]]
    text_bundle_options = _model_bundle_options(text_bundles, str(selection.get("text_bundle_id")) if selection.get("text_bundle_id") else None)
    vision_bundle_options = _model_bundle_options(vision_bundles, str(selection.get("vision_bundle_id")) if selection.get("vision_bundle_id") else None)

    stats_html = (
        '<section class="stats">'
        f'<article class="stat-card"><span class="stat-label">Bundles</span><strong class="stat-value">{catalog["summary"]["bundle_count"]}</strong><span class="stat-copy">bundles bajo ai_models</span></article>'
        f'<article class="stat-card"><span class="stat-label">Seleccionables</span><strong class="stat-value">{catalog["summary"]["selectable_bundle_count"]}</strong><span class="stat-copy">locales para texto o visión</span></article>'
        f'<article class="stat-card"><span class="stat-label">Texto</span><strong class="stat-value">{catalog["summary"]["text_bundle_count"]}</strong><span class="stat-copy">con inferencia de texto</span></article>'
        f'<article class="stat-card"><span class="stat-label">Visión</span><strong class="stat-value">{catalog["summary"]["vision_bundle_count"]}</strong><span class="stat-copy">con mmproj local</span></article>'
        '</section>'
    )

    current_html = _card(
        "Estado actual",
        (
            f"<p style='margin-top: 0;'>Texto: <strong>{escape(str(resolved['text']['provider']))}</strong> · <strong>{escape(str(resolved['text']['bundle_id'] or resolved['text']['model_name'] or 'sin selección'))}</strong></p>"
            f"<p>Visión: <strong>{escape(str(resolved['vision']['provider']))}</strong> · <strong>{escape(str(resolved['vision']['bundle_id'] or resolved['vision']['model_name'] or 'sin selección'))}</strong></p>"
            f"<p>LM Studio texto: <code>{escape(str(providers['text']['lmstudio_base_url']))}</code></p>"
            f"<p>Ollama visión: <code>{escape(str(providers['vision']['ollama_base_url']))}</code></p>"
            f"<p>LM Studio visión: <code>{escape(str(providers['vision']['lmstudio_base_url']))}</code></p>"
        ),
        accent="#86efac",
    )

    controls_html = (
        '<article class="control-card">'
        '<h2 class="control-title">Cambiar modelos</h2>'
        '<form id="model-selection-form">'
        '<div class="control-grid">'
        '<section class="control-card">'
        '<h3 class="card-label">Texto</h3>'
        '<div class="control-row">'
        '<label class="control-label" for="text-provider">Proveedor</label>'
        f'<select id="text-provider" class="control-select">'
        f'{_select_option("local", "local", selected=str(selection.get("text_provider")) == "local")}'
        f'{_select_option("lmstudio", "lmstudio", selected=str(selection.get("text_provider")) == "lmstudio")}'
        '</select>'
        '</div>'
        '<div class="control-row">'
        '<label class="control-label" for="text-bundle-id">Bundle local</label>'
        f'<select id="text-bundle-id" class="control-select">{text_bundle_options}</select>'
        '</div>'
        '<div class="control-row">'
        '<label class="control-label" for="text-model-name">Modelo LM Studio</label>'
        f'<input id="text-model-name" class="control-input" type="text" value="{escape(str(selection.get("text_model_name") or ""), quote=True)}" placeholder="Modelo expuesto por LM Studio">'
        '</div>'
        f'<p class="secondary-note">Selección actual: {escape(str(selection.get("text_provider")))} · {escape(str(selection.get("text_bundle_id") or selection.get("text_model_name") or "sin selección"))}</p>'
        '</section>'
        '<section class="control-card">'
        '<h3 class="card-label">Visión</h3>'
        '<div class="control-row">'
        '<label class="control-label" for="vision-provider">Proveedor</label>'
        f'<select id="vision-provider" class="control-select">'
        f'{_select_option("local", "local", selected=str(selection.get("vision_provider")) == "local")}'
        f'{_select_option("ollama", "ollama", selected=str(selection.get("vision_provider")) == "ollama")}'
        f'{_select_option("lmstudio", "lmstudio", selected=str(selection.get("vision_provider")) == "lmstudio")}'
        '</select>'
        '</div>'
        '<div class="control-row">'
        '<label class="control-label" for="vision-bundle-id">Bundle local</label>'
        f'<select id="vision-bundle-id" class="control-select">{vision_bundle_options}</select>'
        '</div>'
        '<div class="control-row">'
        '<label class="control-label" for="vision-model-name">Modelo remoto</label>'
        f'<input id="vision-model-name" class="control-input" type="text" value="{escape(str(selection.get("vision_model_name") or ""), quote=True)}" placeholder="Modelo de Ollama o LM Studio">'
        '</div>'
        f'<p class="secondary-note">Selección actual: {escape(str(selection.get("vision_provider")))} · {escape(str(selection.get("vision_bundle_id") or selection.get("vision_model_name") or "sin selección"))}</p>'
        '</section>'
        '</div>'
        '<button type="submit" class="save-button">Guardar selección</button>'
        '</form>'
        '</article>'
    )

    bundle_cards_html = "".join(
        _bundle_card(bundle, text_selection=str(selection.get("text_bundle_id")) if selection.get("text_bundle_id") else None, vision_selection=str(selection.get("vision_bundle_id")) if selection.get("vision_bundle_id") else None)
        for bundle in bundles
    )
    bundles_html = _card(
        "Bundles locales",
        bundle_cards_html or '<p class="empty-state">No hay bundles GGUF en ai_models todavía.</p>',
        accent="#7dd3fc",
    )

    body_html = stats_html + current_html + controls_html + bundles_html
    extra_js = """
<script>
(() => {
  const form = document.getElementById('model-selection-form');
  const setBundle = (fieldId, bundleId) => {
    const field = document.getElementById(fieldId);
    if (field) {
      field.value = bundleId || '';
    }
  };
  document.querySelectorAll('[data-select-text-bundle]').forEach((button) => {
    button.addEventListener('click', () => setBundle('text-bundle-id', button.dataset.selectTextBundle));
  });
  document.querySelectorAll('[data-select-vision-bundle]').forEach((button) => {
    button.addEventListener('click', () => setBundle('vision-bundle-id', button.dataset.selectVisionBundle));
  });
  if (!form) {
    return;
  }
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = {
      text_provider: document.getElementById('text-provider').value,
      text_bundle_id: document.getElementById('text-bundle-id').value || null,
      text_model_name: document.getElementById('text-model-name').value.trim() || null,
      vision_provider: document.getElementById('vision-provider').value,
      vision_bundle_id: document.getElementById('vision-bundle-id').value || null,
      vision_model_name: document.getElementById('vision-model-name').value.trim() || null,
    };
    const response = await fetch('/api/models/selection', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const text = await response.text();
      alert(`No se pudo guardar la selección: ${text}`);
      return;
    }
    window.location.reload();
  });
})();
</script>
"""
    return HTMLResponse(
        _page(
            title=title,
            eyebrow=eyebrow,
            headline=headline,
            description=description,
            body_html=body_html,
            extra_js=extra_js,
        )
    )


@router.get("/")
async def landing_page(request: Request) -> HTMLResponse:
    context = get_app_context_from_request(request)
    storage = _get_storage(request)
    overview = storage.overview()

    body_html = (
        '<section class="stats">'
      f'<article class="stat-card"><span class="stat-label">Públicos</span><strong class="stat-value">{overview["public_file_count"]}</strong><span class="stat-copy">archivos en /public</span></article>'
      f'<article class="stat-card"><span class="stat-label">Uploads</span><strong class="stat-value">{overview["upload_file_count"]}</strong><span class="stat-copy">archivos en /uploads</span></article>'
      f'<article class="stat-card"><span class="stat-label">Vault</span><strong class="stat-value">{escape(str(overview["vault_dir"]))}</strong><span class="stat-copy">raíz local del storage</span></article>'
        '</section>'
        '<section class="panel-grid">'
        f'{_card("Panel de almacenamiento", "<p>Explora los uploads, la raíz pública y el estado general del almacén local.</p>", accent="#86efac")}'
        f'{_card("Panel de administración", "<p>Revisa seguridad, modelos locales y el mapa de rutas de la aplicación.</p>", accent="#f59e0b")}'
        f'{_card("Accesos rápidos", "<div class=\"card-actions\"><a class=\"link-button\" href=\"/admin\">Abrir admin</a><a class=\"link-button\" href=\"/admin/routes\">Ver rutas</a><a class=\"link-button\" href=\"/admin/models\">Ver modelos</a></div>", accent="#7dd3fc")}'
        '</section>'
        '<section class="panel" style="margin-top: 18px;">'
        '<h2 class="panel-title">Estado del runtime</h2>'
        f'<div class="panel-body">Servicio activo: <strong>{escape(context.settings.app_name)}</strong>. La interfaz de vistas vive ahora en <code>app/adapters/web</code>.</div>'
        '</section>'
    )
    return HTMLResponse(
        _page(
            title=f"{context.settings.app_name} | Centro de control",
            eyebrow="Vista general",
            headline="Centro de control",
            description="Navega el almacenamiento, las herramientas administrativas y los módulos locales desde un único punto de entrada.",
            body_html=body_html,
        )
    )


@router.get("/admin")
async def admin_page(request: Request) -> HTMLResponse:
    context = get_app_context_from_request(request)
    storage = _get_storage(request)
    overview = storage.overview()

    body_html = (
        '<section class="stats">'
      f'<article class="stat-card"><span class="stat-label">Públicos</span><strong class="stat-value">{overview["public_file_count"]}</strong><span class="stat-copy">archivos visibles públicamente</span></article>'
      f'<article class="stat-card"><span class="stat-label">Uploads</span><strong class="stat-value">{overview["upload_file_count"]}</strong><span class="stat-copy">cargas registradas</span></article>'
        f'<article class="stat-card"><span class="stat-label">Rutas</span><strong class="stat-value">{len(context.module_groups)}</strong><span class="stat-copy">grupos de módulos registrados</span></article>'
        '</section>'
        '<section class="panel-grid">'
        f'{_card("Seguridad local", "<p>El acceso al panel se mantiene restringido a la red local, con rate limiting y ban list activados.</p>", accent="#86efac")}'
        f'{_card("Catálogo de modelos", "<p>Administra los bundles locales y la selección activa de texto o visión.</p><div class=\"card-actions\"><a class=\"link-button\" href=\"/admin/models\">Abrir catálogo</a></div>", accent="#7dd3fc")}'
        f'{_card("Visualizador de rutas", "<p>Inspecciona todas las rutas HTTP, websockets y mounts registradas en el arranque.</p><div class=\"card-actions\"><a class=\"link-button\" href=\"/admin/routes\">Abrir visualizador</a></div>", accent="#f59e0b")}'
        '</section>'
        '<section class="panel" style="margin-top: 18px;">'
        '<h2 class="panel-title">Rutas de storage</h2>'
        f'<div class="panel-body">La API de storage expone <code>/api/storage/overview</code>, <code>/api/storage/public</code> y <code>/api/storage/uploads</code>. La vista raíz y el panel se centralizan en el módulo web dedicado.</div>'
        '</section>'
    )
    return HTMLResponse(
        _page(
            title=f"{context.settings.app_name} | Panel de administración",
            eyebrow="Administración",
            headline="Panel de administración",
            description="Concentra las funciones operativas del sistema en una sola vista.",
            body_html=body_html,
        )
    )


@router.get("/admin/routes")
async def route_visualizer_page(request: Request) -> HTMLResponse:
  return _render_route_inventory_page(
        request,
        title=f"{get_app_context_from_request(request).settings.app_name} | Visualizador de rutas",
        eyebrow="Mapa de rutas",
        headline="Visualizador de rutas",
        description="Revisa cómo se distribuyen las rutas por módulo, incluyendo las APIs, los mounts y los websockets.",
    )


@router.get("/admin/models")
async def models_admin_page(request: Request) -> HTMLResponse:
  return _render_model_catalog_page(
        request,
        title=f"{get_app_context_from_request(request).settings.app_name} | Catálogo de modelos",
        eyebrow="Catálogo AI",
        headline="Modelos y proveedores",
        description="Explora los bundles locales de ai_models, ve qué soporta texto o visión y cambia la selección activa sin tocar la consola.",
    )
