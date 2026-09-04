# SPDX-License-Identifier: MPL-2.0

import asyncio

import pytest
from starlette.testclient import TestClient

from cyberbrain.api.http import create_app
from cyberbrain.core.errors import ConfigurationError
from cyberbrain.core.metrics import MetricsRegistry
from cyberbrain.core.settings import Settings
from cyberbrain.mcp.server import list_tools


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


def test_tool_catalog_contains_canonical_and_legacy_compatibility_tools() -> None:
    tools = asyncio.run(list_tools())
    assert [tool.name for tool in tools] == [
        "help",
        "knowledge_search",
        "knowledge_store",
        "knowledge_timeline",
        "memory_search",
        "memory_store",
        "tech_store",
        "tech_find",
        "ai_memory_read",
        "conversation_save",
        "conversation_recall",
        "dream_enqueue",
        "dream_status",
        "dream_reviews",
        "dream_review_resolve",
    ]
