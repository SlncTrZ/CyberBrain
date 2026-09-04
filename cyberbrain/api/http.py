# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import asynccontextmanager

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from cyberbrain.core.error_model import ErrorEnvelope, ErrorType
from cyberbrain.core.errors import ConfigurationError
from cyberbrain.core.metrics import MetricsRegistry
from cyberbrain.core.settings import Settings
from cyberbrain.mcp.server import server as mcp_server


class StreamableHTTPASGIApp:
    def __init__(self, session_manager: StreamableHTTPSessionManager):
        self._session_manager = session_manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._session_manager.handle_request(scope, receive, send)


def _header_value(scope: Scope, name: bytes) -> str | None:
    expected = name.lower()
    for key, value in scope.get("headers", []):
        if key.lower() == expected:
            return value.decode("latin-1")
    return None


def _authorized(scope: Scope, token: str) -> bool:
    api_key = _header_value(scope, b"x-api-key")
    auth_header = _header_value(scope, b"authorization")

    provided: str | None = None
    if api_key is not None:
        provided = api_key
    elif auth_header is not None and auth_header.lower().startswith("bearer "):
        provided = auth_header[7:].strip()
    return provided == token


class RequireAuthMiddleware:
    def __init__(self, app: ASGIApp, token: str):
        if not token.strip():
            raise ConfigurationError("auth token must not be empty")
        self._app = app
        self._token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        if not _authorized(scope, self._token):
            body = json.dumps(
                ErrorEnvelope(
                    ErrorType.AUTHENTICATION,
                    "authentication required",
                    False,
                ).as_dict()
            ).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"www-authenticate", b"Bearer"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self._app(scope, receive, send)


def create_app(
    settings: Settings,
    *,
    metrics: MetricsRegistry | None = None,
    readiness_probe: Callable[[], None] | None = None,
) -> Starlette:
    settings.validate_runtime()
    session_manager = StreamableHTTPSessionManager(mcp_server, json_response=False)
    raw_mcp = StreamableHTTPASGIApp(session_manager)
    protected_mcp: ASGIApp = (
        RequireAuthMiddleware(raw_mcp, settings.mcp_auth_token or "")
        if settings.require_auth
        else raw_mcp
    )

    async def health(_request):  # noqa: ANN001, ANN202
        return JSONResponse({"status": "ok", "provider": "cyberbrain"})

    async def ready(_request):  # noqa: ANN001, ANN202
        if readiness_probe is None:
            return JSONResponse({"status": "ok", "provider": "cyberbrain"})
        try:
            readiness_probe()
        except Exception:
            return JSONResponse(
                {"status": "unavailable", "provider": "cyberbrain"},
                status_code=503,
            )
        return JSONResponse({"status": "ok", "provider": "cyberbrain"})

    async def metrics_endpoint(request):  # noqa: ANN001, ANN202
        if settings.require_auth and not _authorized(
            request.scope,
            settings.mcp_auth_token or "",
        ):
            return JSONResponse(
                ErrorEnvelope(
                    ErrorType.AUTHENTICATION,
                    "authentication required",
                    False,
                ).as_dict(),
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return JSONResponse((metrics or MetricsRegistry()).snapshot())

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        async with session_manager.run():
            yield

    return Starlette(
        lifespan=lifespan,
        routes=[
            Route("/health", endpoint=health, methods=["GET"]),
            Route("/ready", endpoint=ready, methods=["GET"]),
            Route("/metrics", endpoint=metrics_endpoint, methods=["GET"]),
            Route("/mcp", endpoint=protected_mcp, methods=["GET", "POST", "DELETE"]),
        ],
    )
