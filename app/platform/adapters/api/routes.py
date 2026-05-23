from fastapi import APIRouter, Request

from app.core.app_context import get_app_context_from_request
from app.platform.events import REQUEST_PLATFORM_HEALTH


router = APIRouter(prefix="/api/platform", tags=["platform"])


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_PLATFORM_HEALTH,
        {},
        source_module="platform.adapters.api.routes",
    )