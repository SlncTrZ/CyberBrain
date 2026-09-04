# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from cyberbrain.knowledge.search import KnowledgeSearchService
from cyberbrain.memory.service import MemoryService


class FakeEmbedding:
    dimension = 3
    version = "fake@v1"

    def embed(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class FakeRepository:
    def __init__(self) -> None:
        self.points: dict[UUID, dict[str, Any]] = {}
        self.last_filter: dict[str, Any] | None = None

    def upsert(self, collection: str, *, point_id: UUID, vector, payload) -> None:  # noqa: ANN001
        self.points[point_id] = {"id": str(point_id), "vector": vector, "payload": payload}

    def set_payload(self, collection: str, *, point_id: UUID, payload) -> None:  # noqa: ANN001
        self.points[point_id]["payload"].update(payload)

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
            {"key": "channel", "match": {"value": "chatgpt"}},
            {"key": "project", "match": {"value": "CyberBrain"}},
        ]
    }


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
            {"key": "domain", "match": {"value": "ops"}},
            {"key": "topic", "match": {"value": "mcp"}},
        ]
    }
