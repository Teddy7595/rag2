from __future__ import annotations

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


def _is_local_host(host: str | None) -> bool:
    if not host:
        return False
    if host in {"localhost", "testclient", "::1"}:
        return True
    return host.startswith("127.")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        client = scope.get("client")
        client_host = client[0] if client else None
        is_local_request = _is_local_host(client_host)
        state["client_host"] = client_host
        state["is_local_request"] = is_local_request

        app = scope.get("app")
        context = getattr(getattr(app, "state", None), "context", None)
        settings = getattr(context, "settings", None)
        admin_local_only = getattr(settings, "admin_local_only", True)

        if scope.get("path", "").startswith("/admin") and admin_local_only and not is_local_request:
            response = JSONResponse(
                {"detail": "Admin access restricted to local requests"},
                status_code=403,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)