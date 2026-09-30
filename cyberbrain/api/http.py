# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from contextlib import asynccontextmanager

from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
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
from cyberbrain.tenancy import (
    CallerAuthority,
    IdentityScope,
    OperationClass,
    TrustedIdentityEvidence,
    authority_for_authenticated_scope,
    bind_authority,
    bind_trusted_identity,
)
from cyberbrain.tenancy.principals import PrincipalRegistry


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


def _authentication_source(scope: Scope, token: str) -> str | None:
    api_key = _header_value(scope, b"x-api-key")
    if api_key is not None:
        return "mcp_x_api_key" if hmac.compare_digest(api_key.encode(), token.encode()) else None

    auth_header = _header_value(scope, b"authorization")
    if auth_header is not None and auth_header.lower().startswith("bearer "):
        provided = auth_header[7:].strip()
        return "mcp_bearer" if hmac.compare_digest(provided.encode(), token.encode()) else None
    return None


def _authorized(scope: Scope, token: str) -> bool:
    return _authentication_source(scope, token) is not None


class RequireAuthMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        token: str,
        authority: CallerAuthority,
        *,
        trusted_agent_id: str | None = None,
        registry: PrincipalRegistry | None = None,
    ):
        if not token.strip() and registry is None:
            raise ConfigurationError("auth token must not be empty")
        self._app = app
        self._registry = registry
        self._token = token
        self._authority = authority
        self._trusted_agent_id = trusted_agent_id.strip() if trusted_agent_id else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        principal = None
        if self._registry is None:
            authentication_source = _authentication_source(scope, self._token)
        else:
            api_key = _header_value(scope, b"x-api-key")
            bearer = _header_value(scope, b"authorization") or ""
            credential = api_key if api_key is not None else (
                bearer[7:].strip() if bearer.lower().startswith("bearer ") else ""
            )
            principal = self._registry.authenticate(credential)
            authentication_source = (
                "mcp_x_api_key" if api_key is not None else "mcp_bearer"
            ) if principal is not None else None
        if authentication_source is None:
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

        authority = principal.authority if principal is not None else self._authority
        principal_id = principal.principal_id if principal is not None else "single_owner"
        digest = (
            principal.credential_digest.hex() if principal is not None
            else hashlib.sha256(self._token.encode()).hexdigest()
        )
        scope = {**scope, "user": AuthenticatedUser(AccessToken(
            token=digest, client_id=principal_id, subject=principal_id,
            scopes=sorted(operation.value for operation in authority.grant.operations),
        ))}

        identity_scope = principal.identity_scope if principal is not None else (
            IdentityScope.from_values(agent=self._trusted_agent_id)
            if self._trusted_agent_id is not None else None
        )
        with bind_authority(authority):
            if identity_scope is None:
                await self._app(scope, receive, send)
                return
            identity = TrustedIdentityEvidence.from_authentication_boundary(
                scope=identity_scope,
                authentication_source=authentication_source,
            )
            with bind_trusted_identity(identity):
                await self._app(scope, receive, send)


class BindAuthorityMiddleware:
    def __init__(self, app: ASGIApp, authority: CallerAuthority):
        self._app = app
        self._authority = authority

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        with bind_authority(self._authority):
            await self._app(scope, receive, send)


def create_app(
    settings: Settings,
    *,
    metrics: MetricsRegistry | None = None,
    readiness_probe: Callable[[], None] | None = None,
) -> Starlette:
    settings.validate_runtime()
    session_manager = StreamableHTTPSessionManager(
        mcp_server, json_response=False,
        max_sessions=settings.mcp_max_sessions,
        max_request_body_size=settings.mcp_max_request_bytes,
    )
    raw_mcp = StreamableHTTPASGIApp(session_manager)
    caller_authority = authority_for_authenticated_scope(
        settings.deployment_mode if not settings.principal_registry_file else 'single_owner',
        scope=IdentityScope(),
        operations=frozenset(OperationClass),
    )
    registry = PrincipalRegistry.load(
        settings.principal_registry_file, mode=settings.deployment_mode,
    ) if settings.principal_registry_file else None
    protected_mcp: ASGIApp = (
        RequireAuthMiddleware(
            raw_mcp,
            settings.mcp_auth_token or "",
            caller_authority,
            trusted_agent_id=settings.trusted_agent_id,
            registry=registry,
        )
        if settings.require_auth
        else BindAuthorityMiddleware(raw_mcp, caller_authority)
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
        metrics_scope = None
        metrics_authorized = _authorized(request.scope, settings.mcp_auth_token or "")
        if registry is not None:
            api_key = _header_value(request.scope, b"x-api-key")
            bearer = _header_value(request.scope, b"authorization") or ""
            credential = api_key if api_key is not None else (
                bearer[7:].strip() if bearer.lower().startswith("bearer ") else ""
            )
            principal = registry.authenticate(credential)
            metrics_scope = principal.authority.grant.scope if principal is not None else None
            metrics_authorized = (
                principal is not None
                and OperationClass.ADMIN_REVIEW in principal.authority.grant.operations
            )
        if settings.require_auth and not metrics_authorized:
            return JSONResponse(
                ErrorEnvelope(
                    ErrorType.AUTHENTICATION,
                    "authentication required",
                    False,
                ).as_dict(),
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return JSONResponse((metrics or MetricsRegistry()).snapshot(scope=metrics_scope))

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
