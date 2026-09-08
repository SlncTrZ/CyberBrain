# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from cyberbrain.dreaming import scheduler
from cyberbrain.dreaming.audit import DreamRunAuditStore
from cyberbrain.dreaming.engine import DreamingEngine
from cyberbrain.dreaming.gate import DreamEvidenceGate
from cyberbrain.dreaming.promotion import DreamPromotionCoordinator
from cyberbrain.dreaming.queue import DreamQueue
from cyberbrain.dreaming.reasoner import (
    DreamCandidate,
    DreamReasoningRequest,
    DreamReasoningResult,
    EvidenceItem,
)
from cyberbrain.dreaming.session import QdrantSessionEpisodeLoader
from cyberbrain.dreaming.worker import DreamWorker
from cyberbrain.dreaming.writeback import (
    DreamKnowledgeWriter,
    DreamWritebackCoordinator,
    DreamWriteStatus,
)
from cyberbrain.knowledge.evolution import KnowledgeEvolutionService
from cyberbrain.memory.service import MemoryService
from cyberbrain.schemas.models import Origin, Verification


class FakeEmbedding:
    dimension = 3
    version = "fake@v1"

    def embed(self, text: str) -> list[float]:
        assert text.strip()
        return [0.1, 0.2, 0.3]


class LifecycleRepository:
    def __init__(self) -> None:
        self.collections: dict[str, dict[UUID, dict[str, Any]]] = {}

    def _points(self, collection: str) -> dict[UUID, dict[str, Any]]:
        return self.collections.setdefault(collection, {})

    @staticmethod
    def _value(payload: dict[str, Any], key: str) -> Any:
        current: Any = payload
        for part in key.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    @classmethod
    def _matches(cls, payload: dict[str, Any], qdrant_filter: dict[str, Any] | None) -> bool:
        for condition in (qdrant_filter or {}).get("must", []):
            key = str(condition.get("key") or "")
            match = condition.get("match") or {}
            value = cls._value(payload, key)
            if "value" in match and value != match["value"]:
                return False
            if "any" in match and value not in match["any"]:
                return False
        return True

    def upsert(
        self,
        collection: str,
        *,
        point_id: UUID,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        self._points(collection)[point_id] = {
            "id": str(point_id),
            "vector": list(vector),
            "payload": dict(payload),
        }

    def set_payload(
        self,
        collection: str,
        *,
        point_id: UUID,
        payload: dict[str, Any],
    ) -> None:
        self._points(collection)[point_id]["payload"].update(payload)

    def retrieve(
        self,
        collection: str,
        point_id: UUID,
        *,
        qdrant_filter: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        point = self._points(collection).get(point_id)
        if point is None or not self._matches(point["payload"], qdrant_filter):
            return None
        return point

    def search(
        self,
        collection: str,
        *,
        vector: list[float],
        limit: int,
        qdrant_filter: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        del vector, score_threshold
        return [
            {**point, "score": 0.9}
            for point in self._points(collection).values()
            if self._matches(point["payload"], qdrant_filter)
        ][:limit]

    def scroll(
        self,
        collection: str,
        *,
        qdrant_filter: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return [
            point
            for point in self._points(collection).values()
            if self._matches(point["payload"], qdrant_filter)
        ][:limit]


class AnchorRetriever:
    def __init__(self, evidence: EvidenceItem) -> None:
        self._evidence = evidence

    def recall(self, *, topic, bucket, limit):  # noqa: ANN001, ANN201
        del topic, bucket
        return [self._evidence][:limit]


class LifecycleReasoner:
    def reason(self, request: DreamReasoningRequest) -> DreamReasoningResult:
        topic = request.focal_topics[0]
        evidence_ids = [item.id for item in request.evidence_by_topic[topic]]
        return DreamReasoningResult(
            request_id=request.request_id,
            candidates=[
                DreamCandidate(
                    entity_name="server_owned_post_storage_cognition",
                    entity_type="lesson",
                    summary="CyberBrain owns post-storage cognition.",
                    content=(
                        "External agents produce memory while CyberBrain performs post-storage "
                        "Dreaming and evidence-gated Knowledge Evolution."
                    ),
                    evidence_ids=evidence_ids,
                    confidence=1.0,
                    classification="new_knowledge",
                    context={"topic": topic},
                )
            ],
        )


def test_memory_store_enters_server_owned_dream_and_evolution_pipeline(
    tmp_path, monkeypatch
) -> None:
    repository = LifecycleRepository()
    embedding = FakeEmbedding()
    episodic_collection = "cyberbrain_episodic"
    knowledge_collection = "cyberbrain_knowledge"
    memory = MemoryService(
        repository=repository,
        embedding=embedding,
        collection=episodic_collection,
    )
    evolution = KnowledgeEvolutionService(
        repository=repository,
        embedding=embedding,
        collection=knowledge_collection,
    )

    anchor = evolution.store(
        content="The post-storage lifecycle belongs to the CyberBrain cognitive backend.",
        domain="architecture",
        topic="post-storage",
        entity_type="concept",
        entity_name="post_storage_domain_anchor",
        project="CyberBrain",
        verification=Verification.TESTED,
        origin=Origin.INGESTION,
    ).record

    event_time = datetime.now(UTC) - timedelta(hours=2)
    episodes = [
        memory.store(
            content=f"Post-storage observation {index}: CyberBrain owns cognition processing.",
            session_id="session-auto-cognition",
            event_time=event_time + timedelta(minutes=index),
            agent="coding-agent",
            project="CyberBrain",
            topic="post-storage",
            source="integration_test",
        )
        for index in range(3)
    ]
    assert {episode.dream_status.value for episode in episodes} == {"pending"}

    monkeypatch.setattr(
        scheduler,
        "qdrant_scroll_pending",
        lambda: repository.scroll(
            episodic_collection,
            qdrant_filter={
                "must": [{"key": "dream_status", "match": {"value": "pending"}}]
            },
            limit=100,
        ),
    )
    queue_path = tmp_path / "dream_queue.sqlite"
    monkeypatch.setenv("CYBERBRAIN_DREAM_QUEUE_DB", str(queue_path))
    monkeypatch.setenv("CYBERBRAIN_DREAM_SCHEDULER_QUIET_MINUTES", "60")

    schedule_result = scheduler.run_once(dry_run=False)
    assert schedule_result["enqueued_sessions"] == 1

    queue = DreamQueue(queue_path)
    queued = queue.get_by_session("session-auto-cognition")
    assert queued.status == "pending"
    assert queued.topics == ["post-storage"]

    anchor_evidence = EvidenceItem(
        id=str(anchor.id),
        record_type="knowledge",
        content=anchor.content,
        score=0.9,
        event_time=anchor.updated_at,
        metadata={
            "domain": anchor.domain,
            "topic": anchor.topic,
            "project": anchor.project,
            "verification": anchor.verification.value,
            "status": anchor.status.value,
        },
    )
    engine = DreamingEngine(
        retriever=AnchorRetriever(anchor_evidence),
        reasoner=LifecycleReasoner(),
    )
    audit = DreamRunAuditStore(tmp_path / "dream_audit.sqlite")
    worker = DreamWorker(
        queue=queue,
        session_loader=QdrantSessionEpisodeLoader(
            repository=repository,
            collection=episodic_collection,
        ),
        engine=engine,
        promotion=DreamPromotionCoordinator(
            gate=DreamEvidenceGate(),
            audit_store=audit,
        ),
        writeback=DreamWritebackCoordinator(
            writer=DreamKnowledgeWriter(evolution),
            audit_store=audit,
        ),
    )

    result = worker.process_next()

    assert result is not None
    assert result.status == "processed"
    assert len(result.writes) == 1
    assert result.writes[0].status == DreamWriteStatus.WRITTEN
    promoted = result.writes[0].evolution
    assert promoted is not None
    assert promoted.record.entity_name == "server_owned_post_storage_cognition"
    assert promoted.record.origin.value == "dream"
    assert promoted.record.dream_run_id == result.dream_run_id
    assert promoted.record.verification.value == "tested"

    stored_episodes = repository.scroll(
        episodic_collection,
        qdrant_filter={
            "must": [{"key": "session_id", "match": {"value": "session-auto-cognition"}}]
        },
        limit=100,
    )
    assert len(stored_episodes) == 3
    assert {point["payload"]["dream_status"] for point in stored_episodes} == {"processed"}
    assert {point["payload"]["dream_run_id"] for point in stored_episodes} == {
        result.dream_run_id
    }
    assert queue.get_by_session("session-auto-cognition").status == "processed"
