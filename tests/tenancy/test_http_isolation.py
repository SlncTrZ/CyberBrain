# SPDX-License-Identifier: MPL-2.0
"""Exercise the real MCP HTTP session boundary with colliding caller identities."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from starlette.testclient import TestClient

import cyberbrain.mcp.server as mcp_server
from cyberbrain.api.http import create_app
from cyberbrain.cognition.prediction import PredictionLearningService
from cyberbrain.core.metrics import MetricsRegistry
from cyberbrain.core.settings import Settings
from cyberbrain.dreaming.audit import DreamRunAuditStore
from cyberbrain.dreaming.operations import DreamOperations
from cyberbrain.dreaming.queue import DreamQueue
from cyberbrain.knowledge.evolution import KnowledgeEvolutionService
from cyberbrain.knowledge.search import KnowledgeSearchService
from cyberbrain.memory.service import MemoryService
from cyberbrain.tenancy import DeploymentMode
from tests.tenancy.test_runtime_enforcement import CountingEmbedding, ScopedRepository


def rpc(client, token, method, params, *, session=None, rpc_id=1):
    headers = {"Authorization": "Bearer " + token,
               "Accept": "application/json, text/event-stream"}
    if session:
        headers["Mcp-Session-Id"] = session
    message = {"jsonrpc": "2.0", "method": method, "params": params}
    if rpc_id is not None:
        message["id"] = rpc_id
    response = client.post("/mcp", headers=headers, json=message)
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        data = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
        payload = json.loads(data[-1]) if data else None
    else:
        payload = response.json() if response.content else None
    return response, payload


def initialize(client, token):
    response, result = rpc(client, token, "initialize", {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "isolation-fixture", "version": "fixture"},
    })
    assert response.status_code == 200, response.text
    assert "result" in result
    session = response.headers["mcp-session-id"]
    initialized, _ = rpc(client, token, "notifications/initialized", {},
                         session=session, rpc_id=None)
    assert initialized.status_code == 202
    return session


def call(client, token, session, name, arguments):
    response, result = rpc(client, token, "tools/call",
                           {"name": name, "arguments": arguments}, session=session)
    assert response.status_code == 200, response.text
    assert "result" in result, result
    return json.loads(result["result"]["content"][0]["text"])


def test_real_http_mcp_colliding_agents_and_sessions_never_cross_tenants(tmp_path, monkeypatch):
    definitions = {"schema": 1, "principals": [{
        "principal_id": name, "credential_env": "FIXTURE_" + name.upper(),
        "scope": {"tenant": name, "user": "same-user", "agent": "same-agent"},
        "operations": ["read", "write", "admin_review", "background_reasoning"],
    } for name in ("one", "two")]}
    registry = tmp_path / "principals.json"
    registry.write_text(json.dumps(definitions))
    for name in ("one", "two"):
        monkeypatch.setenv("FIXTURE_" + name.upper(), "fixture-" + name)
    repo = ScopedRepository()
    embedding = CountingEmbedding()
    memory = MemoryService(repository=repo, embedding=embedding, collection="episode")
    runtime = SimpleNamespace(
        metrics=MetricsRegistry(), quota_limiter=None, cognition_path=None,
        memory=memory,
        knowledge_search=KnowledgeSearchService(
            repository=repo, embedding=embedding, collection="knowledge",
        ),
        knowledge_evolution=KnowledgeEvolutionService(
            repository=repo, embedding=embedding, collection="knowledge",
        ),
        prediction_learning=PredictionLearningService(
            memory=memory, repository=repo, episodic_collection="episode",
        ),
    )
    queue = DreamQueue(tmp_path / "queue.sqlite")
    monkeypatch.setattr(mcp_server, "_runtime", runtime)
    monkeypatch.setattr(mcp_server, "_dream_operations", DreamOperations(
        queue=queue, audit=DreamRunAuditStore(tmp_path / "audit.sqlite"),
    ))
    settings = Settings(
        deployment_mode=DeploymentMode.MULTI_USER, principal_registry_file=str(registry),
        quota_requests_per_minute=100, quota_writes_per_minute=100,
        quota_recall_limit=50, quota_dream_enqueues_per_hour=100,
        quota_background_runs_per_hour=100,
    )
    from cyberbrain.tenancy.limiter import SQLiteQuotaLimiter
    runtime.quota_limiter = SQLiteQuotaLimiter(tmp_path / "quota.sqlite", settings.quota_policy())
    event = datetime.now(UTC).isoformat()
    with TestClient(create_app(settings)) as client:
        sessions = {name: initialize(client, "fixture-" + name) for name in ("one", "two")}
        ids = {}
        for name in ("one", "two"):
            token = "fixture-" + name
            row = call(client, token, sessions[name], "memory_store", {
                "content": "private experience " + name,
                "session_id": "same-session", "event_time": event, "topic": "scope",
            })
            assert row["tenant"] == name
            ids[name] = row["id"]
            queued = call(client, token, sessions[name], "dream_enqueue", {
                "session_id": "same-session", "topics": [name],
            })
            assert queued["topics"] == [name]
        assert len(queue.pending()) == 2

        own = call(client, "fixture-one", sessions["one"], "memory_search", {
            "query": "private experience", "view": "full",
        })
        assert [row["content"] for row in own] == ["private experience one"]
        foreign = call(client, "fixture-one", sessions["one"], "memory_get", {"id": ids["two"]})
        missing = call(client, "fixture-one", sessions["one"], "memory_get", {
            "id": "00000000-0000-4000-8000-000000000000",
        })
        assert foreign == missing
        queued = call(client, "fixture-one", sessions["one"], "dream_status",
                      {"session_id": "same-session"})
        assert queued["topics"] == ["one"]

        predictions = {}
        for name in ("one", "two"):
            prediction = call(client, "fixture-" + name, sessions[name], "prediction_record", {
                "expected_outcome": "prospective fixture " + name, "confidence": 0.8,
                "session_id": "same-session", "event_time": event,
            })
            assert prediction["tenant"] == name
            assert prediction["identity_trust"] == "authenticated"
            predictions[name] = prediction["id"]
        pending = call(client, "fixture-one", sessions["one"], "prediction_pending", {})
        assert [item["prediction_id"] for item in pending["items"]] == [predictions["one"]]
        before = len(repo.points)
        denied = call(client, "fixture-one", sessions["one"], "prediction_resolve", {
            "prediction_id": predictions["two"], "observed_outcome": "foreign",
            "assessment": "confirmed", "event_time": event,
        })
        assert "error" in denied
        assert len(repo.points) == before

        response, _ = rpc(client, "fixture-two", "tools/list", {}, session=sessions["one"])
        assert response.status_code == 404

        from cyberbrain.tenancy.quota import QuotaLimit, QuotaPolicy, QuotaResource
        runtime.quota_limiter = SQLiteQuotaLimiter(
            tmp_path / "recall-quota.sqlite",
            QuotaPolicy((QuotaLimit(QuotaResource.RECALL_LIMIT, 50),)),
        )
        denied = call(client, "fixture-one", sessions["one"], "knowledge_timeline", {
            "domain": "engineering", "topic": "scope",
            "entity_type": "policy", "entity_name": "fixture",
        })
        assert "error" in denied
        allowed = call(client, "fixture-one", sessions["one"], "knowledge_timeline", {
            "domain": "engineering", "topic": "scope",
            "entity_type": "policy", "entity_name": "fixture", "limit": 10,
        })
        assert allowed == []
        runtime.quota_limiter = SQLiteQuotaLimiter(tmp_path / "bounded-quota.sqlite", QuotaPolicy((
            QuotaLimit(QuotaResource.REQUESTS, 1, 60),
        )))
        call(client, "fixture-one", sessions["one"], "memory_search", {"query": "private"})
        before = (len(repo.points), embedding.calls)
        denied = call(client, "fixture-one", sessions["one"], "memory_store", {
            "content": "over-budget", "session_id": "same-session", "event_time": event,
        })
        assert "error" in denied
        assert (len(repo.points), embedding.calls) == before
        allowed = call(
            client, "fixture-two", sessions["two"], "memory_search", {"query": "private"},
        )
        assert {row['tenant'] for row in allowed} == {'two'}
