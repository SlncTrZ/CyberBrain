# SPDX-License-Identifier: MPL-2.0

import asyncio

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from cyberbrain.api.http import RequireAuthMiddleware, create_app
from cyberbrain.core.errors import ConfigurationError
from cyberbrain.core.metrics import MetricsRegistry
from cyberbrain.core.settings import Settings
from cyberbrain.mcp.server import list_tools
from cyberbrain.tenancy import (
    DeploymentMode,
    IdentityScope,
    OperationClass,
    authority_for_authenticated_scope,
    current_authority,
)


def make_settings(token: str | None = "secret") -> Settings:
    return Settings(mcp_auth_token=token, require_auth=True)


def test_missing_auth_token_fails_closed() -> None:
    with pytest.raises(ConfigurationError):
        create_app(make_settings(token=None))


def test_health_is_public_and_lightweight() -> None:
    app = create_app(make_settings())
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "provider": "cyberbrain"}


def test_ready_reports_dependency_failure_without_leaking_details() -> None:
    def broken_probe() -> None:
        raise RuntimeError("secret backend detail")

    app = create_app(make_settings(), readiness_probe=broken_probe)
    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "provider": "cyberbrain",
    }
    assert "secret backend detail" not in response.text


def test_ready_reports_ok_when_dependencies_are_available() -> None:
    called = []

    def probe() -> None:
        called.append(True)

    app = create_app(make_settings(), readiness_probe=probe)
    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "provider": "cyberbrain"}
    assert called == [True]


def test_metrics_requires_auth_and_returns_numeric_snapshot() -> None:
    metrics = MetricsRegistry()
    metrics.increment("dream_jobs_processed_total", 2)
    metrics.observe("dream_job_seconds", 1.5)
    app = create_app(make_settings(), metrics=metrics)
    with TestClient(app) as client:
        unauthorized = client.get("/metrics")
        authorized = client.get(
            "/metrics",
            headers={"Authorization": "Bearer secret"},
        )
    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    payload = authorized.json()
    assert payload["counters"] == {"dream_jobs_processed_total": 2}
    assert payload["timings"]["dream_job_seconds"]["count"] == 1
    assert payload["timings"]["dream_job_seconds"]["avg"] == 1.5
    assert "content" not in str(payload).casefold()
    assert "evidence" not in str(payload).casefold()


def test_metrics_is_available_without_auth_only_when_auth_is_disabled() -> None:
    settings = Settings(mcp_auth_token=None, require_auth=False)
    app = create_app(settings, metrics=MetricsRegistry())
    with TestClient(app) as client:
        response = client.get("/metrics")
    assert response.status_code == 200
    assert response.json() == {"counters": {}, "timings": {}}


def test_authenticated_request_binds_single_owner_authority() -> None:
    authority = authority_for_authenticated_scope(
        DeploymentMode.SINGLE_OWNER,
        scope=IdentityScope(),
        operations=frozenset(OperationClass),
    )

    async def probe(_request):  # noqa: ANN001, ANN202
        active = current_authority()
        assert active is not None
        assert active.deployment_mode is DeploymentMode.SINGLE_OWNER
        assert active.grant.operations == frozenset(OperationClass)
        return JSONResponse({"ok": True})

    app = RequireAuthMiddleware(
        Starlette(routes=[Route("/", endpoint=probe, methods=["GET"])]),
        "secret",
        authority,
    )
    with TestClient(app) as client:
        response = client.get("/", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert current_authority() is None


def test_mcp_rejects_missing_auth() -> None:
    app = create_app(make_settings())
    with TestClient(app) as client:
        response = client.post("/mcp")
    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "type": "authentication_error",
            "message": "authentication required",
            "retryable": False,
        }
    }


def test_mcp_rejects_wrong_auth() -> None:
    app = create_app(make_settings())
    with TestClient(app) as client:
        response = client.post("/mcp", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_mcp_can_run_without_auth_when_explicitly_disabled() -> None:
    settings = Settings(mcp_auth_token=None, require_auth=False)
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post("/mcp")
    assert response.status_code != 401


def test_mcp_accepts_bearer_auth_to_reach_protocol_layer() -> None:
    app = create_app(make_settings())
    with TestClient(app) as client:
        response = client.post("/mcp", headers={"Authorization": "Bearer secret"})
    assert response.status_code != 401


def test_tool_catalog_describes_server_owned_post_storage_boundary() -> None:
    tools = {tool.name: tool for tool in asyncio.run(list_tools())}

    assert (
        "server-owned pending Dream lifecycle automatically"
        in tools["memory_store"].description
    )
    assert (
        "not required for ordinary memory read/write usage"
        in tools["prediction_pending"].description
    )
    assert (
        "ordinary pending episodes are scheduled server-side"
        in tools["dream_enqueue"].description
    )


def test_tool_catalog_contains_canonical_and_legacy_compatibility_tools() -> None:
    tools = asyncio.run(list_tools())
    assert [tool.name for tool in tools] == [
        "help",
        "knowledge_search",
        "knowledge_get",
        "knowledge_store",
        "knowledge_timeline",
        "memory_search",
        "memory_get",
        "memory_store",
        "prediction_record",
        "prediction_resolve",
        "prediction_observe",
        "prediction_pending",
        "calibration_observe",
        "tech_store",
        "tech_find",
        "ai_memory_read",
        "conversation_save",
        "conversation_recall",
        "dream_enqueue",
        "dream_status",
        "dream_reason_claim",
        "dream_reason_submit",
        "dream_reviews",
        "dream_review_resolve",
    ]
