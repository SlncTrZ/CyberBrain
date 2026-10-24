# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from cyberbrain.relations.index import INDEX_KEY
from cyberbrain.tenancy.durable import bind_job_authority
from scripts.autolink_knowledge_graph import autolink_knowledge_graph


class MockRepo:
    def __init__(self, points):
        self.points = {p["id"]: p for p in points}

    def scroll_page(self, collection, qdrant_filter=None, limit=100, offset=None):
        return list(self.points.values())[:limit], None

    def search(self, collection, vector, limit, score_threshold=None, qdrant_filter=None):
        # Return all points except vector self
        results = []
        for p in self.points.values():
            results.append({"id": p["id"], "payload": p["payload"], "score": 0.85})
        return results[:limit]

    def retrieve(self, collection, point_id, qdrant_filter=None):
        return self.points.get(str(point_id))

    def set_payload(self, collection, point_id, payload):
        self.points[str(point_id)]["payload"].update(payload)


def test_autolink_creates_edges():
    id1 = str(uuid4())
    id2 = str(uuid4())
    now = datetime.now(UTC).isoformat()
    points = [
        {
            "id": id1,
            "vector": [0.1, 0.2, 0.3],
            "payload": {
                "id": id1,
                "schema_version": 2,
                "record_type": "knowledge",
                "record_class": "knowledge",
                "status": "active",
                "content": "Kafka message queue",
                "domain": "engineering",
                "topic": "messaging",
                "entity_type": "infra",
                "entity_name": "kafka",
                "content_hash": "hash1",
                "created_at": now,
                "updated_at": now,
                "extensions": {},
            },
        },
        {
            "id": id2,
            "vector": [0.1, 0.2, 0.3],
            "payload": {
                "id": id2,
                "schema_version": 2,
                "record_type": "knowledge",
                "record_class": "knowledge",
                "status": "active",
                "content": "Event-driven pub/sub architecture",
                "domain": "engineering",
                "topic": "messaging",
                "entity_type": "architecture",
                "entity_name": "pubsub",
                "content_hash": "hash2",
                "created_at": now,
                "updated_at": now,
                "extensions": {},
            },
        },
    ]

    repo = MockRepo(points)
    with bind_job_authority(None):
        result = autolink_knowledge_graph(
            repository=repo,
            collection="test_knowledge",
            score_threshold=0.7,
            limit_per_record=1,
            max_records=10,
            status="accepted",
            dry_run=False,
        )

    assert result["records_scanned"] == 2
    assert result["edges_created"] > 0
    assert result["records_updated"] > 0

    p1 = repo.points[id1]
    assert "relations" in p1["payload"]["extensions"]
    assert INDEX_KEY in p1["payload"]["extensions"]
    assert len(p1["payload"]["extensions"][INDEX_KEY]["target_keys"]) > 0


def test_autolink_with_embedding_fallback():
    id1 = str(uuid4())
    id2 = str(uuid4())
    now = datetime.now(UTC).isoformat()
    # Points with vector=None (as returned by Qdrant scroll_page)
    points = [
        {
            "id": id1,
            "vector": None,
            "payload": {
                "id": id1,
                "schema_version": 2,
                "record_type": "knowledge",
                "record_class": "knowledge",
                "status": "active",
                "content": "PostgreSQL relational database",
                "domain": "engineering",
                "topic": "storage",
                "entity_type": "database",
                "entity_name": "postgres",
                "content_hash": "hash_pg",
                "created_at": now,
                "updated_at": now,
                "extensions": {},
            },
        },
        {
            "id": id2,
            "vector": None,
            "payload": {
                "id": id2,
                "schema_version": 2,
                "record_type": "knowledge",
                "record_class": "knowledge",
                "status": "active",
                "content": "SQL query optimization",
                "domain": "engineering",
                "topic": "storage",
                "entity_type": "optimization",
                "entity_name": "sql_opt",
                "content_hash": "hash_sql",
                "created_at": now,
                "updated_at": now,
                "extensions": {},
            },
        },
    ]

    class FakeEmbedding:
        def embed(self, text):
            return [0.1, 0.2, 0.3]

    repo = MockRepo(points)
    result = autolink_knowledge_graph(
        repository=repo,
        collection="test_knowledge",
        embedding=FakeEmbedding(),
        score_threshold=0.7,
        limit_per_record=1,
        max_records=10,
        status="proposed",
        dry_run=False,
    )

    assert result["records_scanned"] == 2
    assert result["edges_created"] > 0
    p1 = repo.points[id1]
    assert p1["payload"]["extensions"]["relations"]["edges"][0]["status"] == "proposed"

