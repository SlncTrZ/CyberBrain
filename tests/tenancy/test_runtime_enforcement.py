# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from cyberbrain.cognition.runtime_path import CognitiveRuntimePath
from cyberbrain.core.errors import ConfigurationError
from cyberbrain.dreaming.session import QdrantSessionEpisodeLoader
from cyberbrain.knowledge.evolution import KnowledgeEvolutionService
from cyberbrain.knowledge.search import KnowledgeSearchService
from cyberbrain.memory.service import MemoryService
from cyberbrain.schemas.models import DreamStatus
from cyberbrain.tenancy import (
    DeploymentMode,
    IdentityScope,
    OperationClass,
    authority_for_authenticated_scope,
    bind_authority,
)
from tests.test_services import FakeEmbedding, FakeRepository


def authority(*, operations=None, **scope):
    return authority_for_authenticated_scope(
        DeploymentMode.SINGLE_OWNER,
        scope=IdentityScope.from_values(**scope),
        operations=frozenset(operations if operations is not None else OperationClass),
    )


def matches(payload, condition):
    if "must" in condition and not all(matches(payload, x) for x in condition["must"]):
        return False
    if "must_not" in condition and any(matches(payload, x) for x in condition["must_not"]):
        return False
    if "should" in condition and not any(matches(payload, x) for x in condition["should"]):
        return False
    if "is_empty" in condition:
        return payload.get(condition["is_empty"]["key"]) in (None, "")
    if "key" in condition:
        value = payload.get(condition["key"])
        match = condition.get("match", {})
        if "value" in match:
            return value == match["value"]
        if "any" in match:
            return value in match["any"]
    return True


class ScopedRepository(FakeRepository):
    def search(self, collection, *, vector, limit, qdrant_filter=None, score_threshold=None):
        self.last_filter = qdrant_filter
        return [
            {**point, "score": 0.9} for point in self.points.values()
            if matches(point["payload"], qdrant_filter or {})
        ][:limit]

    def scroll(self, collection, *, qdrant_filter=None, limit=100):
        self.last_filter = qdrant_filter
        return [
            point for point in self.points.values()
            if matches(point["payload"], qdrant_filter or {})
        ][:limit]


class CountingEmbedding(FakeEmbedding):
    def __init__(self):
        self.calls = 0

    def embed(self, text):
        self.calls += 1
        return super().embed(text)


@pytest.fixture
def services():
    repo = ScopedRepository()
    embedding = CountingEmbedding()
    return SimpleNamespace(
        repository=repo,
        embedding=embedding,
        memory=MemoryService(repository=repo, embedding=embedding, collection="episode"),
        knowledge_search=KnowledgeSearchService(
            repository=repo, embedding=embedding, collection="knowledge",
        ),
        knowledge_evolution=KnowledgeEvolutionService(
            repository=repo, embedding=embedding, collection="knowledge",
        ),
    )


@pytest.mark.parametrize("kind", ["memory", "knowledge"])
def test_all_identity_dimensions_filter_before_payload_visibility(services, kind):
    inside = dict(tenant="t", user="u", agent="a", project="p", session_id="s")
    outside = {**inside, "tenant": "other"}
    for index, identity in enumerate([inside, outside], 1):
        services.repository.upsert(
            "record", point_id=UUID(int=index), vector=[0.1, 0.2, 0.3],
            payload={**identity, "content": str(index), "status": "active"},
        )
    with bind_authority(authority(tenant="t", user="u", agent="a", project="p", session="s")):
        service = services.memory if kind == "memory" else services.knowledge_search
        rows = service.search(query="record")
    assert [row["content"] for row in rows] == ["1"]
    assert {"tenant", "user", "agent", "project", "session_id"}.issubset(
        {c["key"] for c in services.repository.last_filter["must"] if "key" in c}
    )


@pytest.mark.parametrize("selector", ["other", "*", "allowed,other"])
def test_denied_selector_has_no_embedding_or_storage_side_effects(services, selector):
    with bind_authority(authority(project="allowed")):
        with pytest.raises((ConfigurationError, ValueError)):
            services.memory.search(query="private", project=selector)
    assert services.embedding.calls == 0
    assert not services.repository.points


def test_write_attribution_inherits_scope_and_rejects_ambiguity(services):
    with bind_authority(authority(tenant="t", user="u", agent="a", project="p", session="s")):
        record = services.memory.store(
            content="experience", event_time=datetime.now(UTC), session_id="s",
        )
    assert (record.tenant, record.user, record.agent, record.project) == ("t", "u", "a", "p")
    count = services.embedding.calls
    with bind_authority(authority(project=["p", "q"])):
        with pytest.raises(ConfigurationError):
            services.memory.store(content="ambiguous", event_time=datetime.now(UTC), session_id="s")
    assert services.embedding.calls == count
    assert len(services.repository.points) == 1


def test_entity_versions_and_retry_are_partitioned_by_identity(services):
    common = dict(domain="ops", topic="routing", entity_type="decision", entity_name="route")
    with bind_authority(authority(project="p", agent="a")):
        first = services.knowledge_evolution.store(content="first policy", **common)
    with bind_authority(authority(project="q", agent="a")):
        second = services.knowledge_evolution.store(content="second policy", **common)
    with bind_authority(authority(project="p", agent="a")):
        retry = services.knowledge_evolution.store(content="first policy", **common)
        revised = services.knowledge_evolution.store(content="revised first policy", **common)
    assert second.record.version == 1
    assert second.previous_id is None
    assert retry.record.id == first.record.id
    assert revised.previous_id == first.record.id
    assert services.repository.points[second.record.id]["payload"]["status"] == "active"


@pytest.mark.parametrize("tool", [
    "knowledge_search", "memory_search", "knowledge_timeline", "tech_find",
    "ai_memory_read", "conversation_recall", "dream_reviews", "dream_reason_claim",
])
def test_mcp_read_and_background_tools_require_operation_grant(monkeypatch, services, tool):
    import cyberbrain.mcp.server as server

    monkeypatch.setattr(server, "_runtime", services)
    dispatched = []
    monkeypatch.setattr(server, "_dispatch_tool", lambda *args: dispatched.append(args))
    with bind_authority(authority(operations={OperationClass.WRITE})):
        result = asyncio.run(server.call_tool(tool, {"query": "x"}))
    assert "error" in json.loads(result[0].text)
    assert not dispatched
    assert services.embedding.calls == 0


@pytest.mark.parametrize("tool", [
    "knowledge_store", "memory_store", "tech_store", "conversation_save",
    "prediction_record", "prediction_resolve", "dream_enqueue", "dream_reason_submit",
])
def test_mcp_write_tools_require_write_grant(monkeypatch, services, tool):
    import cyberbrain.mcp.server as server

    monkeypatch.setattr(server, "_runtime", services)
    dispatched = []
    monkeypatch.setattr(server, "_dispatch_tool", lambda *args: dispatched.append(args))
    with bind_authority(authority(operations={OperationClass.READ})):
        result = asyncio.run(server.call_tool(tool, {}))
    assert "error" in json.loads(result[0].text)
    assert not dispatched
    assert not services.repository.points


@pytest.mark.parametrize("tool", ["dream_reviews", "dream_enqueue", "prediction_pending"])
def test_owner_global_state_is_fail_closed_for_scoped_callers(monkeypatch, services, tool):
    import cyberbrain.mcp.server as server

    monkeypatch.setattr(server, "_runtime", services)
    with bind_authority(authority(project="p")):
        result = asyncio.run(server.call_tool(tool, {}))
    assert "error" in json.loads(result[0].text)


@pytest.mark.parametrize("tool", ["knowledge_store", "memory_store"])
def test_caller_cannot_forge_authenticated_write_metadata(monkeypatch, services, tool):
    import cyberbrain.mcp.server as server

    monkeypatch.setattr(server, "_runtime", services)
    with bind_authority(authority()):
        result = asyncio.run(server.call_tool(tool, {"identity_trust": "authenticated"}))
    assert "error" in json.loads(result[0].text)
    assert services.embedding.calls == 0


def test_cognition_cache_identity_includes_authority_scope():
    with bind_authority(authority(tenant="t1", project="p")):
        first = CognitiveRuntimePath._scope_marker(None, project="p")
    with bind_authority(authority(tenant="t2", project="p")):
        second = CognitiveRuntimePath._scope_marker(None, project="p")
    assert first != second


def test_background_session_read_and_status_update_stay_in_scope(services):
    for agent in ["a", "b"]:
        services.memory.store(
            content=f"experience-{agent}", session_id="s", agent=agent,
            event_time=datetime.now(UTC),
        )
    loader = QdrantSessionEpisodeLoader(repository=services.repository, collection="episode")
    with bind_authority(authority(agent="a", session="s")):
        rows = loader.load("s")
        count = loader.update_status("s", status=DreamStatus.PROCESSED)
    assert [row.content for row in rows] == ["experience-a"]
    assert count == 1
    assert sorted(p["payload"]["dream_status"] for p in services.repository.points.values()) == [
        "pending", "processed",
    ]


def test_mcp_scoped_recall_keeps_other_project_untouched(monkeypatch, services):
    import cyberbrain.mcp.server as server
    from tests.test_cognitive_runtime_path import _path

    common = dict(domain="engineering", topic="adapter", entity_type="note", entity_name="design")
    allowed = services.knowledge_evolution.store(
        content="adapter design allowed", project="p", **common,
    )
    denied = services.knowledge_evolution.store(
        content="adapter design other", project="q", **common,
    )
    services.cognition_path = _path(services.repository, services.knowledge_evolution)
    monkeypatch.setattr(server, "_runtime", services)
    with bind_authority(authority(project="p")):
        result = asyncio.run(server.call_tool(
            "knowledge_search", {"query": "adapter design", "limit": 5},
        ))
        rows = json.loads(result[0].text)
        exact = asyncio.run(server.call_tool("knowledge_get", {"id": str(denied.record.id)}))
    assert [row["id"] for row in rows] == [str(allowed.record.id)]
    assert "_cognition" in rows[0]
    assert services.repository.points[allowed.record.id]["payload"]["access_count"] == 1
    assert services.repository.points[denied.record.id]["payload"]["access_count"] == 0
    assert "error" in json.loads(exact[0].text)
