from fastapi import FastAPI

from app.core.app_context import get_app_context_from_app
from app.core.events import EventEnvelope
from app.platform.application import PlatformService
from app.platform.events import REQUEST_PLATFORM_HEALTH


def register_platform_event_handlers(app: FastAPI) -> None:
    context = get_app_context_from_app(app)
    service = context.services.get("platform")
    if not isinstance(service, PlatformService):
        raise RuntimeError("Platform service not registered")

    def handle_health(envelope: EventEnvelope[dict]) -> dict[str, object]:
        del envelope
        return service.health()

    context.event_bus.subscribe_request(REQUEST_PLATFORM_HEALTH, handle_health)