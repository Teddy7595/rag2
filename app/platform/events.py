from app.core.events import EventChannel, EventKind, EventSpec


REQUEST_PLATFORM_HEALTH = EventSpec[dict, dict](
    name="platform.health",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=dict,
    output_type=dict,
)


__all__ = ["REQUEST_PLATFORM_HEALTH"]