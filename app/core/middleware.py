from __future__ import annotations

import asyncio
from collections import deque
from time import monotonic

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


def _is_local_host(host: str | None) -> bool:
    if not host:
        return False
    if host in {"localhost", "testclient", "::1"}:
        return True
    return host.startswith("127.")


def _path_is_allowed_remote_admin(path: str, allowed_prefixes: tuple[str, ...]) -> bool:
    normalized = str(path or "").strip()
    if not normalized:
        return False
    for prefix in allowed_prefixes:
        value = str(prefix or "").strip()
        if not value:
            continue
        if normalized == value or normalized.startswith(f"{value}/"):
            return True
    return False


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._request_timestamps: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def _is_rate_limited(self, client_key: str, *, window_seconds: int, max_requests: int) -> bool:
        now = monotonic()
        cutoff = now - window_seconds

        async with self._lock:
            timestamps = self._request_timestamps.setdefault(client_key, deque())
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()
            if len(timestamps) >= max_requests:
                return True
            timestamps.append(now)
            return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        client = scope.get("client")
        client_host = client[0] if client else None
        is_local_request = _is_local_host(client_host)
        client_key = (client_host or "unknown").strip().lower()
        state["client_host"] = client_host
        state["is_local_request"] = is_local_request
        state["security_client_key"] = client_key

        app = scope.get("app")
        context = getattr(getattr(app, "state", None), "context", None)
        settings = getattr(context, "settings", None)
        admin_local_only = getattr(settings, "admin_local_only", True)
        admin_remote_allow_paths = tuple(getattr(settings, "admin_remote_allow_paths", ()) or ())

        banned_hosts = set(getattr(settings, "ban_list", ()))
        if client_key in banned_hosts:
            response = JSONResponse(
                {"detail": "Client is banned", "client_host": client_host},
                status_code=403,
            )
            await response(scope, receive, send)
            return

        rate_limit_window_seconds = getattr(settings, "rate_limit_window_seconds", 60)
        rate_limit_max_requests = getattr(settings, "rate_limit_max_requests", 120)
        if await self._is_rate_limited(
            client_key,
            window_seconds=rate_limit_window_seconds,
            max_requests=rate_limit_max_requests,
        ):
            response = JSONResponse(
                {
                    "detail": "Rate limit exceeded",
                    "limit": rate_limit_max_requests,
                    "window_seconds": rate_limit_window_seconds,
                },
                status_code=429,
                headers={"Retry-After": str(rate_limit_window_seconds)},
            )
            await response(scope, receive, send)
            return

        path = str(scope.get("path", "") or "")
        if (
            path.startswith("/admin")
            and admin_local_only
            and not is_local_request
            and not _path_is_allowed_remote_admin(path, admin_remote_allow_paths)
        ):
            response = JSONResponse(
                {"detail": "Admin access restricted to local requests"},
                status_code=403,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)