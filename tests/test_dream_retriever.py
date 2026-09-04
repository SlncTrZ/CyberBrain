# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime
from typing import Any

from cyberbrain.dreaming.planner import TemporalBucket
from cyberbrain.dreaming.retriever import QdrantEvidenceRetriever


class FakeEmbedding:
    dimension = 3
    version = "fake@v1"

    def embed(self, text: str) -> list[float]:
        assert text == "CyberBrain"
        return [0.1, 0.2, 0.3]


class FakeRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(
        self,
        collection: str,
        *,
        vector: list[float],
        limit: int,
        qdrant_filter: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "collection": collection,
                "vector": vector,
                "limit": limit,
                "filter": qdrant_filter,
            }
        )
        if collection == "episodic":
            return [
                {
                    "id": "11111111-1111-4111-8111-111111111111",
                    "score": 0.92,
                    "payload": {
                        "content": "episodic evidence",
                        "event_time": "2026-08-20T12:00:00Z",
                        "session_id": "s1",
                        "topic": "CyberBrain",
                        "project": "brain",
                    },
                }
            ]
        return [
            {
                "id": "22222222-2222-4222-8222-222222222222",
                "score": 0.95,
                "payload": {
                    "content": "knowledge evidence",
                    "updated_at": "2026-08-21T12:00:00Z",
                    "domain": "architecture",
                    "topic": "CyberBrain",
                    "project": "brain",
                    "verification": "tested",
                    "version": 3,
                    "status": "active",
                    "entity_type": "decision",
                    "entity_name": "reasoner_boundary",
                },
            }
        ]


def test_retriever_applies_temporal_filters_and_preserves_metadata() -> None:
    repo = FakeRepository()
    retriever = QdrantEvidenceRetriever(
        repository=repo,
        embedding=FakeEmbedding(),
        knowledge_collection="knowledge",
        episodic_collection="episodic",
    )
    bucket = TemporalBucket(
        name="1_to_4_weeks",
        start=datetime(2026, 8, 7, tzinfo=UTC),
        end=datetime(2026, 8, 28, tzinfo=UTC),
    )

    items = retriever.recall(topic="CyberBrain", bucket=bucket, limit=5)

    assert [item.record_type for item in items] == ["knowledge", "episode"]
    assert items[0].metadata["domain"] == "architecture"
    assert items[0].metadata["verification"] == "tested"
    assert items[0].metadata["entity_name"] == "reasoner_boundary"
    assert items[1].metadata["session_id"] == "s1"

    episodic_filter = repo.calls[0]["filter"]
    knowledge_filter = repo.calls[1]["filter"]
    assert episodic_filter == {
        "must": [
            {
                "key": "event_time",
                "range": {
                    "lte": "2026-08-28T00:00:00+00:00",
                    "gt": "2026-08-07T00:00:00+00:00",
                },
            }
        ]
    }
    assert knowledge_filter["must"][0] == {
        "key": "status",
        "match": {"value": "active"},
    }
    assert knowledge_filter["must"][1]["key"] == "updated_at"


def test_oldest_bucket_has_no_lower_bound() -> None:
    bucket = TemporalBucket(
        name="older_than_1y",
        start=None,
        end=datetime(2025, 9, 4, tzinfo=UTC),
    )

    result = QdrantEvidenceRetriever._range(bucket)

    assert result == {"lte": "2025-09-04T00:00:00+00:00"}
