from __future__ import annotations

from html import escape

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.core.app_context import get_app_context_from_request
from app.models.service import ModelCatalogService


class ModelSelectionUpdate(BaseModel):
    text_provider: str | None = None
    text_bundle_id: str | None = None
    text_model_name: str | None = None
    vision_provider: str | None = None
    vision_bundle_id: str | None = None
    vision_model_name: str | None = None


router = APIRouter(tags=["models"])


def _get_model_service(request: Request) -> ModelCatalogService:
    context = get_app_context_from_request(request)
    service = context.services.get("models")
    if not isinstance(service, ModelCatalogService):
        raise RuntimeError("Model catalog service not registered")
    return service


def _card(title: str, content_html: str, *, accent: str = "#38bdf8") -> str:
    return (
        '<article style="background: rgba(8, 15, 32, 0.82); border: 1px solid rgba(148, 163, 184, 0.18); '
        'border-radius: 20px; padding: 20px; box-shadow: 0 24px 72px rgba(2, 6, 23, 0.32); backdrop-filter: blur(18px);">'
        '<div style="display: flex; align-items: start; justify-content: space-between; gap: 16px;">'
        f'<h2 style="margin: 0; font-size: 1.1rem; color: {accent};">{escape(title)}</h2>'
        '</div>'
        f'<div style="margin-top: 14px; color: #cbd5e1; line-height: 1.65;">{content_html}</div>'
        '</article>'
    )


def _pill(text: str, accent: str, *, uppercase: bool = True) -> str:
    transform = "uppercase" if uppercase else "none"
    return (
        f'<span class="pill" style="--pill-accent: {accent}; text-transform: {transform};">'
        f"{escape(text)}"
        '</span>'
    )


def _select_option(value: str, label: str, *, selected: bool = False) -> str:
    selected_attr = ' selected' if selected else ''
    return f'<option value="{escape(value, quote=True)}"{selected_attr}>{escape(label)}</option>'


def _bundle_options(bundles: list[dict[str, object]], selected_bundle_id: str | None) -> str:
    if not bundles:
        return _select_option('', 'Sin modelos locales', selected=True)
    return ''.join(
        _select_option(
            str(bundle['bundle_id']),
            f"{bundle['display_name']} ({'texto' if bundle['supports_text'] else 'sin texto'}{' / visión' if bundle['supports_vision'] else ''})",
            selected=str(bundle['bundle_id']) == selected_bundle_id,
        )
        for bundle in bundles
    )


def _render_artifacts(artifacts: list[dict[str, object]]) -> str:
    if not artifacts:
        return '<li style="opacity: 0.75;">Sin artefactos GGUF registrados.</li>'
    return ''.join(
        (
            '<li style="margin-bottom: 8px;">'
            f'<strong style="color: #f8fafc;">{escape(str(artifact["file_name"]))}</strong> '
            f'<span style="color: #94a3b8;">{escape(str(artifact["kind"]))} · {escape(str(artifact["size_label"]))}</span>'
            f'<div style="color: #7dd3fc; word-break: break-all;">{escape(str(artifact["relative_path"]))}</div>'
            '</li>'
        )
        for artifact in artifacts
    )


def _bundle_card(bundle: dict[str, object]) -> str:
    badges: list[str] = []
    if bundle['supports_text']:
        badges.append(_pill('texto', '#10b981'))
    if bundle['supports_vision']:
        badges.append(_pill('visión', '#a78bfa'))
    if bundle['is_embedding_cache']:
        badges.append(_pill('cache embeddings', '#fbbf24', uppercase=False))
    if not badges:
        badges.append(_pill('sin selección', '#94a3b8', uppercase=False))

    actions: list[str] = []
    if bundle['supports_text'] and not bundle['is_embedding_cache']:
        actions.append(
            f'<button type="button" class="action-button" data-select-text-bundle="{escape(str(bundle["bundle_id"]), quote=True)}">Usar para texto</button>'
        )
    if bundle['supports_vision'] and not bundle['is_embedding_cache']:
        actions.append(
            f'<button type="button" class="action-button" data-select-vision-bundle="{escape(str(bundle["bundle_id"]), quote=True)}">Usar para visión</button>'
        )

    artifacts_html = _render_artifacts(bundle['artifacts'])
    return (
        '<article class="bundle-card">'
        '<div class="bundle-top">'
        f'<div class="bundle-title-wrap"><h3 class="bundle-title">{escape(str(bundle["display_name"]))}</h3><p class="bundle-path">{escape(str(bundle["relative_path"]))}</p></div>'
        f'<div class="bundle-badges">{"".join(badges)}</div>'
        '</div>'
        f'<p class="bundle-meta">{bundle["artifact_count"]} artefactos · {"seleccionable" if bundle["selectable"] else "solo inventario"}</p>'
        f'<ul class="bundle-artifacts">{artifacts_html}</ul>'
        f'<div class="bundle-actions">{"".join(actions)}</div>'
        '</article>'
    )


def _render_page(*, title: str, eyebrow: str, headline: str, description: str, body_html: str) -> str:
    script_html = """
<script>
(() => {
  const save = async (payload) => {
    const response = await fetch('/api/models/selection', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || 'No se pudo guardar la selección');
    }
    window.location.reload();
  };

  document.querySelectorAll('[data-select-text-bundle]').forEach((button) => {
    button.addEventListener('click', () => save({ text_provider: 'local', text_bundle_id: button.dataset.selectTextBundle }));
  });

  document.querySelectorAll('[data-select-vision-bundle]').forEach((button) => {
    button.addEventListener('click', () => save({ vision_provider: 'local', vision_bundle_id: button.dataset.selectVisionBundle }));
  });

  const form = document.getElementById('model-selection-form');
  if (!form) {
    return;
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const textProvider = document.getElementById('text-provider').value;
    const visionProvider = document.getElementById('vision-provider').value;
    const payload = {
      text_provider: textProvider,
      text_bundle_id: textProvider === 'local' ? document.getElementById('text-bundle-id').value || null : null,
      text_model_name: textProvider === 'lmstudio' ? document.getElementById('text-model-name').value || null : null,
      vision_provider: visionProvider,
      vision_bundle_id: visionProvider === 'local' ? document.getElementById('vision-bundle-id').value || null : null,
      vision_model_name: visionProvider === 'ollama' || visionProvider === 'lmstudio' ? document.getElementById('vision-model-name').value || null : null,
    };
    save(payload).catch((error) => window.alert(error.message));
  });
})();
</script>
"""

    return (
        '<!doctype html><html lang="es"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(title)}</title>'
        '<style>'
        ':root { color-scheme: dark; }'
        '* { box-sizing: border-box; }'
        'body { margin: 0; min-height: 100vh; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; '
        'background: radial-gradient(circle at top left, rgba(56, 189, 248, 0.18), transparent 24%), '
        'radial-gradient(circle at top right, rgba(16, 185, 129, 0.14), transparent 22%), '
        'linear-gradient(140deg, #050816 0%, #0f172a 52%, #111827 100%); color: #e2e8f0; }'
        '.page-shell { max-width: 1320px; margin: 0 auto; padding: 48px 20px 72px; }'
        '.hero { display: grid; gap: 18px; margin-bottom: 24px; }'
        '.eyebrow { margin: 0; text-transform: uppercase; letter-spacing: 0.18em; font-size: 0.76rem; color: #7dd3fc; }'
        '.headline { margin: 0; font-size: clamp(2.4rem, 4vw, 4.8rem); line-height: 0.95; max-width: 12ch; }'
        '.description { margin: 0; max-width: 74ch; font-size: 1.02rem; color: #cbd5e1; line-height: 1.7; }'
        '.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 24px; }'
        '.control-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; margin-bottom: 24px; }'
        '.control-card, .bundle-card, .stat-card { background: rgba(8, 15, 32, 0.82); border: 1px solid rgba(148, 163, 184, 0.18); border-radius: 22px; padding: 20px; box-shadow: 0 24px 72px rgba(2, 6, 23, 0.32); backdrop-filter: blur(18px); }'
        '.stat-label { display: block; color: #94a3b8; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px; }'
        '.stat-value { font-size: 1.9rem; font-weight: 700; color: #f8fafc; }'
        '.stat-copy { display: block; margin-top: 6px; color: #cbd5e1; font-size: 0.9rem; }'
        '.control-row { display: grid; gap: 10px; margin-bottom: 14px; }'
        '.control-row label { color: #cbd5e1; font-size: 0.9rem; }'
        '.control-row select, .control-row input { width: 100%; border: 1px solid rgba(148, 163, 184, 0.22); background: rgba(2, 6, 23, 0.6); color: #f8fafc; border-radius: 14px; padding: 12px 14px; font-size: 0.96rem; }'
        '.control-row input::placeholder { color: #64748b; }'
        '.control-row select:focus, .control-row input:focus { outline: none; border-color: rgba(125, 211, 252, 0.75); box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.16); }'
        '.secondary-note { margin: 0; color: #94a3b8; font-size: 0.84rem; line-height: 1.5; }'
        '.save-button, .action-button { border: 0; border-radius: 999px; padding: 11px 16px; font-weight: 700; cursor: pointer; }'
        '.save-button { background: linear-gradient(135deg, #38bdf8, #10b981); color: #03111d; }'
        '.action-button { background: rgba(125, 211, 252, 0.12); color: #7dd3fc; border: 1px solid rgba(125, 211, 252, 0.22); }'
        '.bundle-list { display: grid; gap: 16px; }'
        '.bundle-top { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }'
        '.bundle-title { margin: 0; font-size: 1.08rem; color: #f8fafc; }'
        '.bundle-path { margin: 4px 0 0; color: #94a3b8; font-size: 0.84rem; word-break: break-all; }'
        '.bundle-badges { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }'
        '.bundle-meta { margin: 10px 0 14px; color: #cbd5e1; font-size: 0.9rem; }'
        '.bundle-artifacts { margin: 0; padding-left: 18px; }'
        '.bundle-actions { margin-top: 14px; display: flex; flex-wrap: wrap; gap: 10px; }'
        '.pill { display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; border-radius: 999px; border: 1px solid var(--pill-accent); color: var(--pill-accent); background: rgba(255, 255, 255, 0.04); font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; }'
        '.empty-state { color: #cbd5e1; margin-top: 18px; }'
        '</style>'
        '</head>'
        '<body>'
        '<main class="page-shell">'
        '<section class="hero">'
        f'<p class="eyebrow">{escape(eyebrow)}</p>'
        f'<h1 class="headline">{escape(headline)}</h1>'
        f'<p class="description">{escape(description)}</p>'
        '</section>'
        f'{body_html}'
        '</main>'
        f'{script_html}'
        '</body></html>'
    )


@router.get('/admin/models', response_class=HTMLResponse)
async def models_admin_page(request: Request) -> HTMLResponse:
    context = get_app_context_from_request(request)
    service = _get_model_service(request)
    catalog = service.catalog()
    bundles = catalog['bundles']
    selection = catalog['selection']
    resolved = catalog['resolved']
    providers = catalog['providers']

    text_bundle_options = _bundle_options([bundle for bundle in bundles if bundle['supports_text'] and not bundle['is_embedding_cache']], str(selection.get('text_bundle_id')))
    vision_bundle_options = _bundle_options([bundle for bundle in bundles if bundle['supports_vision'] and not bundle['is_embedding_cache']], str(selection.get('vision_bundle_id')))

    stats_html = (
        '<section class="stats">'
        f'<article class="stat-card"><span class="stat-label">Bundles</span><strong class="stat-value">{catalog["summary"]["bundle_count"]}</strong><span class="stat-copy">bundles bajo ai_models</span></article>'
        f'<article class="stat-card"><span class="stat-label">Seleccionables</span><strong class="stat-value">{catalog["summary"]["selectable_bundle_count"]}</strong><span class="stat-copy">locales para texto o visión</span></article>'
        f'<article class="stat-card"><span class="stat-label">Texto</span><strong class="stat-value">{catalog["summary"]["text_bundle_count"]}</strong><span class="stat-copy">con inferencia de texto</span></article>'
        f'<article class="stat-card"><span class="stat-label">Visión</span><strong class="stat-value">{catalog["summary"]["vision_bundle_count"]}</strong><span class="stat-copy">con mmproj local</span></article>'
        '</section>'
    )

    current_html = _card(
        'Estado actual',
        (
            f"<p style='margin-top: 0;'>Texto: <strong>{escape(str(resolved['text']['provider']))}</strong> · <strong>{escape(str(resolved['text']['bundle_id'] or resolved['text']['model_name'] or 'sin selección'))}</strong></p>"
            f"<p>Visión: <strong>{escape(str(resolved['vision']['provider']))}</strong> · <strong>{escape(str(resolved['vision']['bundle_id'] or resolved['vision']['model_name'] or 'sin selección'))}</strong></p>"
            f"<p>LM Studio texto: <code>{escape(str(providers['text']['lmstudio_base_url']))}</code></p>"
            f"<p>Ollama visión: <code>{escape(str(providers['vision']['ollama_base_url']))}</code></p>"
            f"<p>LM Studio visión: <code>{escape(str(providers['vision']['lmstudio_base_url']))}</code></p>"
        ),
        accent='#86efac',
    )

    controls_html = _card(
        'Cambiar modelos',
        (
            '<form id="model-selection-form">'
            '<div class="control-grid">'
            '<section class="control-card">'
            '<h3 style="margin-top: 0;">Texto</h3>'
            '<div class="control-row"><label for="text-provider">Proveedor</label>'
            f'<select id="text-provider">{_select_option("local", "local", selected=str(selection.get("text_provider")) == "local")}{_select_option("lmstudio", "lmstudio", selected=str(selection.get("text_provider")) == "lmstudio")}</select></div>'
            '<div class="control-row"><label for="text-bundle-id">Bundle local</label>'
            f'<select id="text-bundle-id">{text_bundle_options}</select></div>'
            '<div class="control-row"><label for="text-model-name">Modelo LM Studio</label>'
            f'<input id="text-model-name" type="text" value="{escape(str(selection.get("text_model_name") or ""), quote=True)}" placeholder="Modelo expuesto por LM Studio">'
            '</div>'
            f'<p class="secondary-note">Selección actual: {escape(str(selection.get("text_provider")))} · {escape(str(selection.get("text_bundle_id") or selection.get("text_model_name") or "sin selección"))}</p>'
            '</section>'
            '<section class="control-card">'
            '<h3 style="margin-top: 0;">Visión</h3>'
            '<div class="control-row"><label for="vision-provider">Proveedor</label>'
            f'<select id="vision-provider">{_select_option("local", "local", selected=str(selection.get("vision_provider")) == "local")}{_select_option("ollama", "ollama", selected=str(selection.get("vision_provider")) == "ollama")}{_select_option("lmstudio", "lmstudio", selected=str(selection.get("vision_provider")) == "lmstudio")}</select></div>'
            '<div class="control-row"><label for="vision-bundle-id">Bundle local</label>'
            f'<select id="vision-bundle-id">{vision_bundle_options}</select></div>'
            '<div class="control-row"><label for="vision-model-name">Modelo remoto</label>'
            f'<input id="vision-model-name" type="text" value="{escape(str(selection.get("vision_model_name") or ""), quote=True)}" placeholder="Modelo de Ollama o LM Studio">'
            '</div>'
            f'<p class="secondary-note">Selección actual: {escape(str(selection.get("vision_provider")))} · {escape(str(selection.get("vision_bundle_id") or selection.get("vision_model_name") or "sin selección"))}</p>'
            '</section>'
            '</div>'
            '<button type="submit" class="save-button">Guardar selección</button>'
            '</form>'
        ),
        accent='#f59e0b',
    )

    bundle_cards_html = ''.join(_bundle_card(bundle) for bundle in bundles)
    bundles_html = _card(
        'Bundles locales',
        bundle_cards_html or '<p class="empty-state">No hay bundles GGUF en ai_models todavía.</p>',
        accent='#7dd3fc',
    )

    body_html = stats_html + '<section style="display: grid; gap: 18px; margin-bottom: 24px;">' + current_html + controls_html + '</section>' + bundles_html
    return HTMLResponse(
        _render_page(
            title=f"{context.settings.app_name} | Catálogo de modelos",
            eyebrow='Catálogo AI',
            headline='Modelos y proveedores',
            description='Explora los bundles locales de ai_models, ve qué soporta texto o visión y cambia la selección activa sin tocar la consola.',
            body_html=body_html,
        )
    )


@router.get('/api/models/catalog')
async def models_catalog(request: Request) -> dict[str, object]:
    return _get_model_service(request).catalog()


@router.get('/api/models/selection')
async def models_selection(request: Request) -> dict[str, object]:
    return _get_model_service(request).current_selection()


@router.patch('/api/models/selection')
async def update_models_selection(request: Request, payload: ModelSelectionUpdate) -> dict[str, object]:
    return _get_model_service(request).update_selection(payload.model_dump(exclude_none=True))