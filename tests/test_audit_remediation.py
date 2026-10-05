# SPDX-License-Identifier: MPL-2.0
"""Regression tests verifying remediation of findings F01 through F07 from release audit."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from cyberbrain.cognition.prediction import PredictionLearningService
from cyberbrain.dreaming.audit import DreamRunAuditStore
from cyberbrain.dreaming.gate import DreamEvidenceGate, PromotionDecision
from cyberbrain.dreaming.operations import DreamOperations
from cyberbrain.dreaming.queue import DreamQueue
from cyberbrain.dreaming.reasoner import (
    DreamCandidate,
    DreamReasoningRequest,
    DreamReasoningResult,
    EvidenceItem,
)
from cyberbrain.memory.service import MemoryService
from cyberbrain.reasoning.engine import BoundedReasoningEngine
from cyberbrain.reasoning.models import ConflictType
from cyberbrain.relations.models import (
    EntityRef,
    EvidenceRef,
    RelationEdge,
    RelationKind,
    RelationScope,
    RelationStatus,
)
from tests.test_dream_writeback import FakeEmbedding, FakeRepository

NOW = datetime(2026, 9, 9, 4, 0, tzinfo=UTC)


def _entity(name: str, project: str | None = None) -> EntityRef:
    return EntityRef(
        domain="engineering",
        topic="architecture",
        entity_type="module",
        entity_name=name,
        context={},
        scope=RelationScope(project=project),
    )


def _edge(
    kind: RelationKind,
    src: EntityRef,
    tgt: EntityRef,
    *,
    status: RelationStatus = RelationStatus.ACCEPTED,
    valid_from: datetime = NOW,
    valid_until: datetime | None = None,
) -> RelationEdge:
    return RelationEdge(
        kind=kind,
        source=src,
        target=tgt,
        target_record_id=uuid4(),
        evidence=(EvidenceRef(record_type="knowledge", id=uuid4()),),
        status=status,
        valid_from=valid_from,
        valid_until=valid_until,
        review_note="Verified evidence" if status != RelationStatus.PROPOSED else None,
    )


# --- F01: Project-filtered pagination ---
def test_f01_project_pagination_preserves_cursor_and_finds_matching_rows(tmp_path) -> None:
    audit = DreamRunAuditStore(tmp_path / "audit.sqlite")
    queue = DreamQueue(tmp_path / "queue.sqlite")
    operations = DreamOperations(queue=queue, audit=audit)

    request = DreamReasoningRequest(
        request_id="req-f01",
        session_id="s-f01",
        focal_topics=["code"],
        session_start=NOW,
        session_end=NOW,
        evidence_by_topic={"code": []},
    )
    audit.start(dream_run_id="run-f01", request=request)

    # Insert 5 candidates for foreign project, then 2 for CyberBrain
    with audit._connect() as conn:
        for i in range(5):
            cand = DreamCandidate(
                entity_name=f"foreign_{i}",
                entity_type="fact",
                summary="Foreign summary",
                content="Foreign content",
                evidence_ids=[],
                confidence=0.7,
                classification="new_knowledge",
                context={"project": "OtherProject"},
            )
            conn.execute(
                """
                INSERT INTO dream_candidate_decisions (
                    dream_run_id, candidate_index, candidate_json, decision,
                    reasoner_confidence, evidence_strength, promotion_confidence,
                    evidence_ids_json, reasons_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "run-f01",
                    i,
                    json.dumps(cand.__dict__),
                    "review",
                    0.7,
                    0.5,
                    0.6,
                    "[]",
                    "[]",
                    (NOW + timedelta(seconds=i)).isoformat(),
                ),
            )

        for i in range(2):
            idx = 5 + i
            cand = DreamCandidate(
                entity_name=f"cb_{i}",
                entity_type="fact",
                summary=f"CyberBrain summary {i}",
                content=f"CyberBrain content {i}",
                evidence_ids=[],
                confidence=0.8,
                classification="new_knowledge",
                context={"project": "CyberBrain"},
            )
            conn.execute(
                """
                INSERT INTO dream_candidate_decisions (
                    dream_run_id, candidate_index, candidate_json, decision,
                    reasoner_confidence, evidence_strength, promotion_confidence,
                    evidence_ids_json, reasons_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "run-f01",
                    idx,
                    json.dumps(cand.__dict__),
                    "review",
                    0.8,
                    0.5,
                    0.65,
                    "[]",
                    "[]",
                    (NOW + timedelta(seconds=idx)).isoformat(),
                ),
            )

    # Page 1: limit=1, project="CyberBrain"
    page1 = operations.pending_reviews(limit=1, project="CyberBrain")
    assert len(page1) == 1
    assert page1[0]["candidate"]["entity_name"] == "cb_0"
    cursor1 = page1[0]["review_cursor"]
    assert cursor1 is not None

    # Page 2: with cursor
    page2 = operations.pending_reviews(limit=1, cursor=cursor1, project="CyberBrain")
    assert len(page2) == 1
    assert page2[0]["candidate"]["entity_name"] == "cb_1"


# --- F02: Duplicate fingerprinting does not reject distinct content ---
def test_f02_duplicate_fingerprint_does_not_reject_distinct_content() -> None:
    gate = DreamEvidenceGate()
    evidence = [
        EvidenceItem(
            id="11111111-1111-4111-8111-111111111111",
            record_type="knowledge",
            content="Evidence 1",
            metadata={"domain": "ops", "topic": "deploy", "verification": "tested"},
            score=0.9,
            event_time=NOW,
        ),
        EvidenceItem(
            id="22222222-2222-4222-8222-222222222222",
            record_type="knowledge",
            content="Evidence 2",
            metadata={"domain": "ops", "topic": "deploy", "verification": "tested"},
            score=0.9,
            event_time=NOW,
        ),
    ]
    request = DreamReasoningRequest(
        request_id="req-f02",
        session_id="s-f02",
        focal_topics=["deploy"],
        session_start=NOW,
        session_end=NOW,
        evidence_by_topic={"deploy": evidence},
    )

    # Two candidates with SAME summary, but DIFFERENT content
    result_diff_content = DreamReasoningResult(
        request_id="req-f02",
        candidates=[
            DreamCandidate(
                entity_name="deploy_1",
                entity_type="fact",
                summary="Deployment procedure completed.",
                content="Step 1: Check environment and verify network.",
                evidence_ids=["11111111-1111-4111-8111-111111111111"],
                confidence=0.9,
                classification="new_knowledge",
                context={"topic": "deploy"},
            ),
            DreamCandidate(
                entity_name="deploy_2",
                entity_type="fact",
                summary="Deployment procedure completed.",
                content="Step 2: Start services and verify healthcheck endpoint.",
                evidence_ids=["22222222-2222-4222-8222-222222222222"],
                confidence=0.9,
                classification="new_knowledge",
                context={"topic": "deploy"},
            ),
        ],
    )

    eval_diff = gate.evaluate(request, result_diff_content)
    # Neither should be rejected as a duplicate because content is different
    assert eval_diff.candidates[0].decision != PromotionDecision.REJECT
    assert eval_diff.candidates[1].decision != PromotionDecision.REJECT

    # True duplicate (identical content/type/topic): collapses without evidence loss
    result_true_dup = DreamReasoningResult(
        request_id="req-f02",
        candidates=[
            DreamCandidate(
                entity_name="deploy_1",
                entity_type="fact",
                summary="Deployment procedure completed.",
                content="Identical content verified across runs.",
                evidence_ids=["11111111-1111-4111-8111-111111111111"],
                confidence=0.9,
                classification="new_knowledge",
                context={"topic": "deploy"},
            ),
            DreamCandidate(
                entity_name="deploy_2",
                entity_type="fact",
                summary="Deployment procedure completed.",
                content="Identical content verified across runs.",
                evidence_ids=["22222222-2222-4222-8222-222222222222"],
                confidence=0.9,
                classification="new_knowledge",
                context={"topic": "deploy"},
            ),
        ],
    )
    eval_dup = gate.evaluate(request, result_true_dup)
    assert eval_dup.candidates[1].decision == PromotionDecision.REJECT
    assert "duplicate_candidate_in_run" in eval_dup.candidates[1].reasons
    # First candidate merged both evidence IDs without evidence loss
    assert set(eval_dup.candidates[0].evidence_ids) == {
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
    }


# --- F03: Counterfactual sandbox internal contradictions ---
def test_f03_counterfactual_sandbox_detects_internal_contradictions() -> None:
    engine = BoundedReasoningEngine()
    ent_a = _entity("feature_x")
    ent_b = _entity("feature_y")

    # Base is empty; hypothetical has internal contradiction
    hypothetical = [
        _edge(RelationKind.SUPPORTS, ent_a, ent_b, status=RelationStatus.PROPOSED),
        _edge(RelationKind.CONTRADICTS, ent_a, ent_b, status=RelationStatus.PROPOSED),
    ]

    res = engine.evaluate_counterfactual(
        hypothetical_edges=hypothetical,
        base_edges=[],
    )

    assert not res.is_consistent
    assert len(res.contradictions) == 1
    assert res.contradictions[0].conflict_type == ConflictType.POLARITY_MISMATCH


# --- F04: Premise status and time interval intersection ---
def test_f04_typed_inference_respects_premise_status_and_time_intervals() -> None:
    engine = BoundedReasoningEngine()
    ent_a = _entity("a")
    ent_b = _entity("b")
    ent_c = _entity("c")

    # 1. Rejected premise must NOT produce inference
    edge_rejected = _edge(RelationKind.DEPENDS_ON, ent_a, ent_b, status=RelationStatus.REJECTED)
    edge_valid = _edge(RelationKind.DEPENDS_ON, ent_b, ent_c, status=RelationStatus.ACCEPTED)
    assert engine.derive_inferences([edge_rejected, edge_valid]) == []

    # 2. Disjoint validity intervals must NOT produce inference
    t1 = NOW
    t2 = NOW + timedelta(days=10)
    t3 = NOW + timedelta(days=20)
    t4 = NOW + timedelta(days=30)
    # AB valid [t1, t2], BC valid [t3, t4] -> disjoint
    edge_ab_disjoint = _edge(RelationKind.DEPENDS_ON, ent_a, ent_b, valid_from=t1, valid_until=t2)
    edge_bc_disjoint = _edge(RelationKind.DEPENDS_ON, ent_b, ent_c, valid_from=t3, valid_until=t4)
    assert engine.derive_inferences([edge_ab_disjoint, edge_bc_disjoint]) == []

    # 3. Overlapping validity intervals produce inference with intersection
    # AB valid [t1, t3], BC valid [t2, t4] -> intersection is [t2, t3]
    edge_ab_overlap = _edge(RelationKind.DEPENDS_ON, ent_a, ent_b, valid_from=t1, valid_until=t3)
    edge_bc_overlap = _edge(RelationKind.DEPENDS_ON, ent_b, ent_c, valid_from=t2, valid_until=t4)
    inferred = engine.derive_inferences([edge_ab_overlap, edge_bc_overlap])
    assert len(inferred) == 1
    assert inferred[0].edge.valid_from == t2
    assert inferred[0].edge.valid_until == t3


# --- F05: Entity keys preserve canonical identity and partition ---
def test_f05_entity_keys_prevent_cross_partition_joins() -> None:
    engine = BoundedReasoningEngine()
    # Same name/domain/topic, but different projects
    ent_a = _entity("a", project="ProjectAlpha")
    ent_b_alpha = _entity("shared_b", project="ProjectAlpha")
    edge_1 = _edge(RelationKind.DEPENDS_ON, ent_a, ent_b_alpha)

    ent_b_beta = _entity("shared_b", project="ProjectBeta")
    ent_c = _entity("c", project="ProjectBeta")
    edge_2 = _edge(RelationKind.DEPENDS_ON, ent_b_beta, ent_c)

    # ent_b_alpha and ent_b_beta belong to different partitions; no false join should occur
    inferred = engine.derive_inferences([edge_1, edge_2])
    assert inferred == []


# --- F06: Correlation ID idempotency after outcome resolution ---
def test_f06_correlation_id_idempotency_after_outcome_resolution() -> None:
    repo = FakeRepository()
    memory = MemoryService(
        repository=repo,
        embedding=FakeEmbedding(),
        collection="cyberbrain_episodic",
    )
    service = PredictionLearningService(
        memory=memory,
        repository=repo,
        episodic_collection="cyberbrain_episodic",
    )

    # Step 1: Record prediction
    pred = service.record_prediction(
        expected_outcome="Job finishes in 10s",
        confidence=0.85,
        session_id="s-lifecycle",
        event_time=NOW,
        correlation_id="corr-lifecycle-100",
    )

    # Step 2: Resolve outcome
    service.record_outcome(
        prediction_id=pred.id,
        observed_outcome="Job finished in 8s",
        assessment="confirmed",
        event_time=NOW + timedelta(seconds=10),
    )

    # Step 3: Retry record_prediction with SAME correlation_id
    retry = service.record_prediction(
        expected_outcome="Job finishes in 10s retry",
        confidence=0.85,
        session_id="s-lifecycle",
        event_time=NOW,
        correlation_id="corr-lifecycle-100",
    )

    # Must return identical prediction ID, not create a duplicate
    assert retry.id == pred.id
    predictions = [
        p for p in repo.points.values() if p["payload"].get("source") == "cognitive_prediction"
    ]
    assert len(predictions) == 1


# --- F07: Reasoning depth enforcement and budget ---
def test_f07_max_depth_enforcement_and_validation() -> None:
    engine = BoundedReasoningEngine()
    ent_a = _entity("m1")
    ent_b = _entity("m2")
    ent_c = _entity("m3")

    edge_ab = _edge(RelationKind.DEPENDS_ON, ent_a, ent_b)
    edge_bc = _edge(RelationKind.DEPENDS_ON, ent_b, ent_c)

    # max_depth=0 must derive 0 inferences
    assert engine.derive_inferences([edge_ab, edge_bc], max_depth=0) == []

    # invalid depth raises ValueError
    with pytest.raises(ValueError, match="max_depth must be between 0 and 5"):
        engine.derive_inferences([edge_ab, edge_bc], max_depth=-1)


# --- F08: Symmetric inference requires verified target anchor ---
def test_f08_symmetric_inference_requires_verified_target_anchor() -> None:
    engine = BoundedReasoningEngine()
    ent_a = _entity("claim_a")
    ent_b = _entity("claim_b")
    uuid_a = uuid4()

    edge_ab = _edge(RelationKind.CONTRADICTS, ent_a, ent_b)

    # Without verified anchor for ent_a, engine must fail closed and NOT fabricate an ID
    assert engine.derive_inferences([edge_ab]) == []

    # With verified anchor for ent_a, engine derives B -> A with target_record_id=uuid_a
    derived = engine.derive_inferences([edge_ab], source_record_ids={ent_a.key: uuid_a})
    assert len(derived) == 1
    assert derived[0].edge.target_record_id == uuid_a
    assert derived[0].edge.source.entity_name == "claim_b"
    assert derived[0].edge.target.entity_name == "claim_a"


# --- F09: Typed evidence union preserves distinct typed proofs ---
def test_f09_typed_evidence_union_preserves_both_knowledge_and_episode() -> None:
    engine = BoundedReasoningEngine()
    ent_a = _entity("svc_a")
    ent_b = _entity("svc_b")
    ent_c = _entity("svc_c")

    shared_uuid = uuid4()
    # Premise AB cites Knowledge proof with shared_uuid
    edge_ab = RelationEdge(
        kind=RelationKind.DEPENDS_ON,
        source=ent_a,
        target=ent_b,
        target_record_id=uuid4(),
        evidence=(EvidenceRef(record_type="knowledge", id=shared_uuid),),
        status=RelationStatus.ACCEPTED,
        valid_from=NOW,
        review_note="Verified note",
    )
    # Premise BC cites Episode proof with SAME shared_uuid
    edge_bc = RelationEdge(
        kind=RelationKind.DEPENDS_ON,
        source=ent_b,
        target=ent_c,
        target_record_id=uuid4(),
        evidence=(EvidenceRef(record_type="episode", id=shared_uuid),),
        status=RelationStatus.ACCEPTED,
        valid_from=NOW,
        review_note="Verified note",
    )

    inferred = engine.derive_inferences([edge_ab, edge_bc])
    assert len(inferred) == 1
    # Both typed proofs must be preserved in derived evidence union
    derived_ev = inferred[0].edge.evidence
    assert len(derived_ev) == 2
    types = {ev.record_type for ev in derived_ev}
    assert types == {"knowledge", "episode"}
    assert all(ev.id == shared_uuid for ev in derived_ev)


# --- F10: Adapter resolve path refuses heuristic correlation on incomplete scan ---
@pytest.mark.asyncio
async def test_f10_partial_pending_scan_refuses_heuristic_correlation() -> None:
    from cyberbrain.agent_adapter.adapter import UniversalAgentAdapter
    from cyberbrain.agent_adapter.models import AgentScope, Observation
    from tests.agent_adapter.fakes import FakeCyberBrainClient

    # Fake client returns a dict with items and may_be_incomplete=True
    class PartialClient(FakeCyberBrainClient):
        async def prediction_pending(self, **kwargs: Any) -> dict[str, Any]:
            return {
                "items": [
                    {
                        "id": "p-single",
                        "correlation_id": "corr-partial-1",
                        "expected_outcome": "Outcome",
                    }
                ],
                "may_be_incomplete": True,
                "returned": 1,
            }

    adapter = UniversalAgentAdapter(PartialClient())
    scope = AgentScope(session_id="s-part", agent="agent-pi")
    obs = Observation(
        observed_outcome="Completed",
        assessment="confirmed",
        event_time=NOW,
        correlation_id="corr-partial-1",
    )

    match, record = await adapter.resolve_prediction(observation=obs, scope=scope)

    # Incomplete scan: must fail closed, NOT resolve based on partial list!
    assert match.prediction_id is None
    assert match.reason_code == "incomplete_scan_cannot_verify_correlation_uniqueness"
    assert record is None
