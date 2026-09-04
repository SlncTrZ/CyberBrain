# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
from contextlib import asynccontextmanager

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from cyberbrain.core.error_model import ErrorEnvelope, ErrorType
from cyberbrain.core.errors import ConfigurationError
from cyberbrain.reasoner_provider.server import server


class StreamableHTTPASGIApp:
    def __init__(self, session_manager: StreamableHTTPSessionManager) -> None:
        self._session_manager = session_manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._session_manager.handle_request(scope, receive, send)


class RequireAuthMiddleware:
    def __init__(self, app: ASGIApp, token: str) -> None:
        if not token.strip():
            raise ConfigurationError("reasoner auth token must not be empty")
        self._app = app
        self._token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        auth = None
        for key, value in scope.get("headers", []):
            if key.lower() == b"authorization":
                auth = value.decode("latin-1")
                break
        provided = None
        if auth and auth.lower().startswith("bearer "):
            provided = auth[7:].strip()
        if provided != self._token:
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


def create_reasoner_app(*, auth_token: str | None = None, require_auth: bool = True) -> Starlette:
    if require_auth and not (auth_token or "").strip():
        raise ConfigurationError("reasoner auth token is required when auth is enabled")

    session_manager = StreamableHTTPSessionManager(server, json_response=False)
    raw = StreamableHTTPASGIApp(session_manager)
    endpoint: ASGIApp = (
        RequireAuthMiddleware(raw, auth_token or "")
        if require_auth
        else raw
    )

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        async with session_manager.run():
            yield

    return Starlette(
        lifespan=lifespan,
        routes=[Route("/mcp", endpoint=endpoint, methods=["GET", "POST", "DELETE"])],
    )
