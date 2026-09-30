# SPDX-License-Identifier: MPL-2.0
"""Authentication chooses persisted server-owned authority; sessions cannot switch principal."""

import hashlib
import json

import pytest
from starlette.testclient import TestClient

from cyberbrain.api.http import RequireAuthMiddleware
from cyberbrain.core.errors import ConfigurationError
from cyberbrain.tenancy import (
    DeploymentMode,
    IdentityScope,
    OperationClass,
    authority_for_authenticated_scope,
    current_authority,
    current_trusted_identity,
)
from cyberbrain.tenancy.principals import (
    AuthenticatedPrincipal,
    PrincipalRegistry,
)


def principal(name, token, tenant):
    scope = IdentityScope.from_values(tenant=tenant, user=name, agent="shared-agent")
    return AuthenticatedPrincipal(
        principal_id=name,
        authority=authority_for_authenticated_scope(
            DeploymentMode.SINGLE_OWNER, scope=scope, operations=frozenset(OperationClass),
        ),
        identity_scope=scope, credential_digest=hashlib.sha256(token.encode()).digest(),
    )


def registry():
    return PrincipalRegistry((principal("one", "fixture-one", "t1"),
                              principal("two", "fixture-two", "t2")))


def test_credential_and_payload_cannot_substitute_bound_principal():
    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        result = {
            "authority": current_authority().grant.scope.as_dict(),
            "identity": current_trusted_identity().scope.as_dict(),
            "sdk_principal": scope["user"].access_token.client_id,
        }
        await send({"type": "http.response.start", "status": 200, "headers": [
            (b"content-type", b"application/json"), (b"mcp-session-id", b"session-one"),
        ]})
        await send({"type": "http.response.body", "body": json.dumps(result).encode()})
    owner = authority_for_authenticated_scope(
        DeploymentMode.SINGLE_OWNER, scope=IdentityScope(), operations=frozenset(OperationClass),
    )
    with TestClient(RequireAuthMiddleware(app, "", owner, registry=registry())) as client:
        first = client.post("/mcp", headers={
            "Authorization": "Bearer fixture-one", "X-Tenant": "t2", "X-Agent": "forged",
        }, json={"tenant": "t2"})
        assert first.json()["authority"]["tenant"] == ["t1"]
        assert first.json()["identity"]["user"] == ["one"]
        own = client.get("/mcp", headers={
            "Authorization": "Bearer fixture-one", "Mcp-Session-Id": "session-one",
        })
        assert own.status_code == 200
        other = client.post("/mcp", headers={"Authorization": "Bearer fixture-two"})
        assert other.json()["sdk_principal"] == "two"
        assert own.json()["sdk_principal"] == "one"
        assert client.post("/mcp", headers={"Authorization": "Bearer bad"}).status_code == 401


def test_registry_configuration_survives_reload_without_storing_credentials(tmp_path, monkeypatch):
    path = tmp_path / "principals.json"
    definition = {"schema": 1, "principals": [{
        "principal_id": "one", "credential_env": "FIXTURE_PRINCIPAL_CREDENTIAL",
        "scope": {"tenant": "t", "user": "u", "agent": "a"},
        "operations": ["read", "write"],
    }]}
    path.write_text(json.dumps(definition))
    monkeypatch.setenv("FIXTURE_PRINCIPAL_CREDENTIAL", "fixture-only-credential")
    first = PrincipalRegistry.load(path, mode=DeploymentMode.MULTI_USER)
    second = PrincipalRegistry.load(path, mode=DeploymentMode.MULTI_USER)
    assert first.authenticate("fixture-only-credential").authority == (
        second.authenticate("fixture-only-credential").authority
    )
    assert "fixture-only-credential" not in path.read_text()
    assert "fixture-only-credential" not in repr(first.authenticate("fixture-only-credential"))
    assert second.authenticate("unknown") is None
    monkeypatch.delenv("FIXTURE_PRINCIPAL_CREDENTIAL")
    with pytest.raises(ConfigurationError, match="invalid principal registry"):
        PrincipalRegistry.load(path, mode=DeploymentMode.MULTI_USER)


@pytest.mark.parametrize("data", [
    {"schema": 2, "principals": []}, {"schema": True, "principals": []},
    {"schema": 1, "principals": []}, {"schema": 1, "principals": [{
        "principal_id": "one", "credential_env": "FIXTURE_PRINCIPAL_CREDENTIAL",
        "scope": {"tenant": "*", "user": "u"}, "operations": ["read"],
    }]},
])
def test_invalid_registry_fails_closed(tmp_path, monkeypatch, data):
    path = tmp_path / "principals.json"
    path.write_text(json.dumps(data))
    monkeypatch.setenv("FIXTURE_PRINCIPAL_CREDENTIAL", "fixture-only")
    with pytest.raises(ConfigurationError):
        PrincipalRegistry.load(path, mode=DeploymentMode.MULTI_USER)


def test_credentials_cannot_be_shared_by_distinct_principals():
    with pytest.raises(ConfigurationError, match="exactly one principal"):
        PrincipalRegistry((principal("one", "same-fixture", "t1"),
                           principal("two", "same-fixture", "t2")))


def test_broader_mode_is_opt_in_and_requires_complete_runtime_limits(tmp_path, monkeypatch):
    from cyberbrain.api.http import create_app
    from cyberbrain.core.settings import Settings
    path = tmp_path / "principals.json"
    path.write_text(json.dumps({"schema": 1, "principals": [{
        "principal_id": "p", "credential_env": "FIXTURE_PRINCIPAL_CREDENTIAL",
        "scope": {"tenant": "t", "user": "u", "agent": "a"}, "operations": ["read", "write"],
    }]}))
    monkeypatch.setenv("FIXTURE_PRINCIPAL_CREDENTIAL", "fixture-only")
    settings = Settings(
        deployment_mode=DeploymentMode.MULTI_USER, principal_registry_file=str(path),
        quota_requests_per_minute=100, quota_writes_per_minute=20,
        quota_recall_limit=10, quota_dream_enqueues_per_hour=10,
        quota_background_runs_per_hour=10,
    )
    settings.validate_runtime()
    with TestClient(create_app(settings)) as client:
        assert client.post("/mcp").status_code == 401
        response = client.get("/metrics", headers={"Authorization": "Bearer fixture-only"})
        assert response.status_code == 401
    settings.quota_background_runs_per_hour = None
    with pytest.raises(ConfigurationError, match="all runtime quota limits"):
        settings.validate_runtime()


def test_request_byte_ceiling_precedes_application_side_effects(monkeypatch):
    import cyberbrain.mcp.server as server
    from cyberbrain.api.http import create_app
    from cyberbrain.core.settings import Settings
    calls = []
    monkeypatch.setattr(server, "_dispatch_tool", lambda *args: calls.append(args))
    app = create_app(Settings(mcp_auth_token="fixture", mcp_max_request_bytes=1024))
    with TestClient(app) as client:
        response = client.post("/mcp", content=b"x" * 2048, headers={
            "Authorization": "Bearer fixture", "Content-Length": "0",
        })
    assert response.status_code == 413
    assert calls == []


def test_sdk_session_capacity_rejects_and_delete_frees_slot():
    from cyberbrain.api.http import create_app
    from cyberbrain.core.settings import Settings
    from tests.tenancy.test_http_isolation import initialize, rpc
    app = create_app(Settings(mcp_auth_token="fixture", mcp_max_sessions=1))
    with TestClient(app) as client:
        session = initialize(client, "fixture")
        response, _ = rpc(client, "fixture", "initialize", {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "fixture", "version": "fixture"},
        })
        assert response.status_code == 503
        deleted = client.delete("/mcp", headers={
            "Authorization": "Bearer fixture", "Mcp-Session-Id": session,
        })
        assert deleted.status_code == 200
        assert initialize(client, "fixture") != session
