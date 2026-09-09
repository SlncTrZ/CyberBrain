# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from cyberbrain.knowledge.search import KnowledgeSearchService
from cyberbrain.memory.service import MemoryService
from cyberbrain.tenancy import (
    DeploymentMode,
    IdentityScope,
    OperationClass,
    authority_for_authenticated_scope,
)


class FakeEmbedding:
    dimension = 3
    version = "fake@v1"

    def embed(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class ShadowRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def submit(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class FakeRepository:
    def __init__(self) -> None:
        self.points: dict[UUID, dict[str, Any]] = {}
        self.last_filter: dict[str, Any] | None = None

    def upsert(self, collection: str, *, point_id: UUID, vector, payload) -> None:  # noqa: ANN001
        self.points[point_id] = {"id": str(point_id), "vector": vector, "payload": payload}

    def set_payload(self, collection: str, *, point_id: UUID, payload) -> None:  # noqa: ANN001
        self.points[point_id]["payload"].update(payload)

    def retrieve(self, collection: str, point_id: UUID, *, qdrant_filter=None):
        self.last_filter = qdrant_filter
        point = self.points.get(point_id)
        if point is None:
            return None
        payload = point["payload"]
        for condition in (qdrant_filter or {}).get("must", []):
            key = condition["key"]
            match = condition["match"]
            value = payload.get(key)
            if "value" in match and value != match["value"]:
                return None
            if "any" in match and value not in match["any"]:
                return None
        return {"id": str(point_id), "payload": payload}

    def search(
        self,
        collection: str,
        *,
        vector,
        limit: int,
        qdrant_filter=None,
        score_threshold=None,
    ):
        self.last_filter = qdrant_filter
        return [
            {
                "id": str(point_id),
                "score": 0.9,
                "payload": point["payload"],
            }
            for point_id, point in list(self.points.items())[:limit]
        ]

    def scroll(self, collection: str, *, qdrant_filter=None, limit: int = 100):
        self.last_filter = qdrant_filter
        return [
            {"id": str(point_id), "payload": point["payload"]}
            for point_id, point in list(self.points.items())[:limit]
        ]


def test_memory_store_and_search_applies_filters() -> None:
    repo = FakeRepository()
    service = MemoryService(
        repository=repo,
        embedding=FakeEmbedding(),
        collection="cyberbrain_episodic",
    )
    record = service.store(
        content="Discussed CyberBrain metadata.",
        session_id="session-1",
        event_time=datetime.now(UTC),
        channel="chatgpt",
        project="CyberBrain",
    )
    results = service.search(query="CyberBrain", channel="chatgpt", project="CyberBrain")

    assert results[0]["id"] == str(record.id)
    assert repo.last_filter == {
        "must": [
            {"key": "ordinary_recall", "match": {"value": True}},
            {"key": "channel", "match": {"value": "chatgpt"}},
            {"key": "project", "match": {"value": "CyberBrain"}},
        ]
    }


def test_exact_fetch_enforces_project_scope_for_knowledge() -> None:
    repo = FakeRepository()
    service = KnowledgeSearchService(
        repository=repo,
        embedding=FakeEmbedding(),
        collection="cyberbrain_knowledge",
    )
    point_id = UUID("11111111-1111-1111-1111-111111111111")
    repo.upsert(
        "cyberbrain_knowledge",
        point_id=point_id,
        vector=[0.1, 0.2, 0.3],
        payload={"project": "alpha", "content": "allowed"},
    )

    allowed = authority_for_authenticated_scope(
        DeploymentMode.AGENT_READY,
        scope=IdentityScope.from_values(agent="agent-a", project="alpha"),
        operations=frozenset({OperationClass.READ}),
    )
    denied = authority_for_authenticated_scope(
        DeploymentMode.AGENT_READY,
        scope=IdentityScope.from_values(agent="agent-a", project="beta"),
        operations=frozenset({OperationClass.READ}),
    )

    assert service.get(point_id=point_id, authority=allowed)["content"] == "allowed"
    assert service.get(point_id=point_id, authority=denied) is None


def test_exact_fetch_enforces_agent_project_and_session_for_memory() -> None:
    repo = FakeRepository()
    service = MemoryService(
        repository=repo,
        embedding=FakeEmbedding(),
        collection="cyberbrain_episodic",
    )
    record = service.store(
        content="private memory",
        session_id="session-a",
        event_time=datetime.now(UTC),
        agent="agent-a",
        project="alpha",
    )

    allowed = authority_for_authenticated_scope(
        DeploymentMode.AGENT_READY,
        scope=IdentityScope.from_values(agent="agent-a", project="alpha", session="session-a"),
        operations=frozenset({OperationClass.READ}),
    )
    denied = authority_for_authenticated_scope(
        DeploymentMode.AGENT_READY,
        scope=IdentityScope.from_values(agent="agent-b", project="alpha", session="session-a"),
        operations=frozenset({OperationClass.READ}),
    )

    assert service.get(point_id=record.id, authority=allowed)["content"] == "private memory"
    assert repo.last_filter == {
        "must": [
            {"key": "agent", "match": {"value": "agent-a"}},
            {"key": "project", "match": {"value": "alpha"}},
            {"key": "session_id", "match": {"value": "session-a"}},
        ]
    }
    assert service.get(point_id=record.id, authority=denied) is None


def test_exact_fetch_fails_closed_for_multi_user_until_identity_fields_exist() -> None:
    repo = FakeRepository()
    service = KnowledgeSearchService(
        repository=repo,
        embedding=FakeEmbedding(),
        collection="cyberbrain_knowledge",
    )
    authority = authority_for_authenticated_scope(
        DeploymentMode.MULTI_USER,
        scope=IdentityScope.from_values(tenant="tenant-a", user="user-a"),
        operations=frozenset({OperationClass.READ}),
    )
    assert service.get(
        point_id=UUID("11111111-1111-1111-1111-111111111111"),
        authority=authority,
    ) is None


def test_knowledge_search_shadow_cannot_replace_vector_rows() -> None:
    repo = FakeRepository()
    shadow = ShadowRecorder()
    service = KnowledgeSearchService(
        repository=repo,
        embedding=FakeEmbedding(),
        collection="cyberbrain_knowledge",
        literal_shadow=shadow,  # type: ignore[arg-type]
    )
    point_id = UUID("22222222-2222-2222-2222-222222222222")
    repo.upsert(
        "cyberbrain_knowledge",
        point_id=point_id,
        vector=[0.1, 0.2, 0.3],
        payload={"status": "active", "domain": "ops", "content": "vector result"},
    )

    rows = service.search(query="commit abc1234", limit=5, domain="ops")

    assert rows == [
        {
            "id": str(point_id),
            "score": 0.9,
            "status": "active",
            "domain": "ops",
            "content": "vector result",
        }
    ]
    assert shadow.calls == [
        {
            "query": "commit abc1234",
            "vector_rows": rows,
            "filters": {
                "status": "active",
                "record_class": "knowledge",
                "ordinary_recall": True,
                "domain": "ops",
            },
            "limit": 5,
        }
    ]


def test_knowledge_search_defaults_to_active_status() -> None:
    repo = FakeRepository()
    service = KnowledgeSearchService(
        repository=repo,
        embedding=FakeEmbedding(),
        collection="cyberbrain_knowledge",
    )
    service.search(query="x", domain="ops", topic="mcp")

    assert repo.last_filter == {
        "must": [
            {"key": "status", "match": {"value": "active"}},
            {"key": "record_class", "match": {"value": "knowledge"}},
            {"key": "ordinary_recall", "match": {"value": True}},
            {"key": "domain", "match": {"value": "ops"}},
            {"key": "topic", "match": {"value": "mcp"}},
        ]
    }
