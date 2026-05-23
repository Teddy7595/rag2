from __future__ import annotations

from html import escape

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

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


@router.get("/api/storage/overview")
async def storage_overview(request: Request) -> dict[str, object]:
    return _get_storage(request).overview()


@router.get("/api/storage/public")
async def list_public_files(request: Request) -> list[str]:
    return list(_get_storage(request).list_public_files())


@router.get("/api/storage/uploads")
async def list_upload_files(request: Request) -> list[str]:
    return list(_get_storage(request).list_upload_files())