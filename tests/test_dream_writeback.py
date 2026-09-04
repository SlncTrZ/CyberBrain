# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from cyberbrain.dreaming.audit import DreamRunAuditStore
from cyberbrain.dreaming.gate import CandidateGateResult, DreamGateResult, PromotionDecision
from cyberbrain.dreaming.operations import DreamOperations
from cyberbrain.dreaming.queue import DreamQueue
from cyberbrain.dreaming.reasoner import (
    DreamCandidate,
    DreamReasoningRequest,
    DreamReasoningResult,
    EvidenceItem,
)
from cyberbrain.dreaming.writeback import (
    DreamKnowledgeWriter,
    DreamWritebackCoordinator,
    DreamWriteStatus,
)
from cyberbrain.knowledge.evolution import KnowledgeEvolutionService


class FakeEmbedding:
    dimension = 3
    version = "fake@v1"

    def embed(self, text: str) -> list[float]:
        assert text.strip()
        return [0.1, 0.2, 0.3]


class FakeRepository:
    def __init__(self) -> None:
        self.points: dict[UUID, dict[str, Any]] = {}

    def upsert(
        self,
        collection: str,
        *,
        point_id: UUID,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        self.points[point_id] = {"id": str(point_id), "vector": vector, "payload": payload}

    def set_payload(
        self,
        collection: str,
        *,
        point_id: UUID,
        payload: dict[str, Any],
    ) -> None:
        self.points[point_id]["payload"].update(payload)

    def search(
        self,
        collection: str,
        *,
        vector: list[float],
        limit: int,
        qdrant_filter: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        result = []
        for point in self.points.values():
            payload = point["payload"]
            if payload.get("status") != "active":
                continue
            if qdrant_filter:
                if not all(
                    payload.get(condition["key"]) == condition["match"]["value"]
                    for condition in qdrant_filter.get("must", [])
                ):
                    continue
            result.append(point)
        return result[:limit]

    def scroll(
        self,
        collection: str,
        *,
        qdrant_filter: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return list(self.points.values())[:limit]


def _service(repo: FakeRepository) -> KnowledgeEvolutionService:
    return KnowledgeEvolutionService(
        repository=repo,
        embedding=FakeEmbedding(),
        collection="cyberbrain_knowledge",
    )


def _request(*, include_domain: bool = True) -> DreamReasoningRequest:
    now = datetime(2026, 9, 4, 2, 0, tzinfo=UTC)
    ids = [
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
        "33333333-3333-4333-8333-333333333333",
    ]
    evidence = []
    for index, evidence_id in enumerate(ids):
        metadata = {
            "topic": "cyberbrain",
            "verification": ["tested", "observed", "user_confirmed"][index],
        }
        if include_domain:
            metadata["domain"] = "architecture"
        evidence.append(
            EvidenceItem(
                id=evidence_id,
                record_type="knowledge" if index != 1 else "episode",
                content=f"evidence {index}",
                score=0.9,
                event_time=now,
                metadata=metadata,
            )
        )
    return DreamReasoningRequest(
        request_id="req-write",
        session_id="session-write",
        focal_topics=["cyberbrain"],
        session_start=now,
        session_end=now,
        evidence_by_topic={"cyberbrain": evidence},
    )


def _result(request: DreamReasoningRequest) -> DreamReasoningResult:
    ids = [item.id for item in request.evidence_by_topic["cyberbrain"]]
    return DreamReasoningResult(
        request_id=request.request_id,
        candidates=[
            DreamCandidate(
                entity_name="open_reasoner_boundary",
                entity_type="lesson",
                summary="Reasoner is implementation agnostic.",
                content="CyberBrain keeps the Reasoner implementation agnostic.",
                evidence_ids=ids,
                confidence=0.91,
                classification="new_knowledge",
                context={"reasoning_section": "durable_lesson", "topic": "cyberbrain"},
            )
        ],
    )


def _gate(request: DreamReasoningRequest) -> DreamGateResult:
    ids = [item.id for item in request.evidence_by_topic["cyberbrain"]]
    return DreamGateResult(
        request_id=request.request_id,
        candidates=[
            CandidateGateResult(
                candidate_index=0,
                decision=PromotionDecision.PROMOTE,
                reasoner_confidence=0.91,
                evidence_strength=0.95,
                promotion_confidence=0.936,
                evidence_ids=ids,
                reasons=["promotion_threshold_met"],
            )
        ],
    )


def test_promoted_dream_writes_provenance_through_evolution() -> None:
    repo = FakeRepository()
    request = _request()
    writer = DreamKnowledgeWriter(_service(repo))

    writes = writer.write_promoted(
        request=request,
        result=_result(request),
        gate=_gate(request),
        dream_run_id="dream-run-write",
    )

    assert writes[0].status == DreamWriteStatus.WRITTEN
    record = writes[0].evolution.record
    assert record.origin.value == "dream"
    assert record.dream_run_id == "dream-run-write"
    assert record.provenance_type == "dream"
    assert record.source == "dream_run:dream-run-write"
    assert record.domain == "architecture"
    assert record.topic == "cyberbrain"
    assert len(record.evidence_ids) == 3
    assert record.confidence == 0.936
    assert record.extensions["evidence_strength"] == 0.95


def test_promoted_dream_blocks_missing_domain_instead_of_guessing() -> None:
    repo = FakeRepository()
    request = _request(include_domain=False)
    writer = DreamKnowledgeWriter(_service(repo))

    writes = writer.write_promoted(
        request=request,
        result=_result(request),
        gate=_gate(request),
        dream_run_id="dream-run-write",
    )

    assert writes[0].status == DreamWriteStatus.BLOCKED_METADATA
    assert not repo.points


def test_writeback_coordinator_records_write_audit(tmp_path) -> None:
    repo = FakeRepository()
    request = _request()
    result = _result(request)
    gate = _gate(request)
    audit = DreamRunAuditStore(tmp_path / "dreaming.sqlite")
    audit.start(dream_run_id="dream-run-write", request=request)
    writer = DreamKnowledgeWriter(_service(repo))
    coordinator = DreamWritebackCoordinator(writer=writer, audit_store=audit)

    writes = coordinator.write_and_audit(
        request=request,
        result=result,
        gate=gate,
        dream_run_id="dream-run-write",
    )

    rows = audit.writes("dream-run-write")
    assert writes[0].status == DreamWriteStatus.WRITTEN
    assert rows[0]["write_status"] == "written"
    assert rows[0]["evolution_outcome"] == "insert_new"
    assert rows[0]["knowledge_id"] == str(writes[0].evolution.record.id)


def test_manual_approval_writes_once_and_is_retry_safe(tmp_path) -> None:
    repo = FakeRepository()
    request = _request()
    result = _result(request)
    evidence_ids = [item.id for item in request.evidence_by_topic["cyberbrain"]]
    gate = DreamGateResult(
        request_id=request.request_id,
        candidates=[
            CandidateGateResult(
                candidate_index=0,
                decision=PromotionDecision.REVIEW,
                reasoner_confidence=0.91,
                evidence_strength=0.72,
                promotion_confidence=0.78,
                evidence_ids=evidence_ids,
                reasons=["promotion_confidence_requires_review"],
            )
        ],
    )
    audit = DreamRunAuditStore(tmp_path / "audit.sqlite")
    audit.start(dream_run_id="dream-run-review", request=request)
    audit.complete(dream_run_id="dream-run-review", result=result, gate=gate)
    operations = DreamOperations(
        queue=DreamQueue(tmp_path / "queue.sqlite"),
        audit=audit,
        writer=DreamKnowledgeWriter(_service(repo)),
    )

    first = operations.review(
        dream_run_id="dream-run-review",
        candidate_index=0,
        resolution="approved",
        reviewer="human:test",
        reason="verified evidence",
    )
    first_knowledge_id = first["write"]["knowledge_id"]
    assert first["write"]["write_status"] == "written"
    assert len(repo.points) == 1

    second = operations.review(
        dream_run_id="dream-run-review",
        candidate_index=0,
        resolution="approved",
        reviewer="human:test",
        reason="retry after response loss",
    )
    assert second["write"]["knowledge_id"] == first_knowledge_id
    assert len(repo.points) == 1
