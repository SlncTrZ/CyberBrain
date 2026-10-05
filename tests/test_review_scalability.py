# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
from datetime import UTC, datetime

from cyberbrain.dreaming.audit import DreamRunAuditStore
from cyberbrain.dreaming.gate import DreamEvidenceGate, PromotionDecision
from cyberbrain.dreaming.operations import DreamOperations
from cyberbrain.dreaming.orchestration import MultipassDreamReasoner
from cyberbrain.dreaming.planner import TopicExtractor
from cyberbrain.dreaming.queue import DreamQueue
from cyberbrain.dreaming.reasoner import (
    DreamCandidate,
    DreamReasoningRequest,
    DreamReasoningResult,
    EvidenceItem,
    ReasoningTaskKind,
)


def test_topic_extractor_filters_functional_stopwords() -> None:
    extractor = TopicExtractor()
    texts = [
        "And the for all with this that they were very and the",
        "Python architecture implementation was tested and verified",
    ]
    topics = extractor.extract(texts, limit=5)
    # Stopwords like "and", "the", "for", "all" must not be extracted
    assert "and" not in [t.casefold() for t in topics]
    assert "the" not in [t.casefold() for t in topics]
    assert "for" not in [t.casefold() for t in topics]
    assert any(t.casefold() in {"python", "architecture", "implementation"} for t in topics)


def test_entity_name_stopword_hygiene() -> None:
    # "and" as a topic must fallback to "topic"
    name1 = MultipassDreamReasoner._entity_name("and", ReasoningTaskKind.CURRENT_STATE, 0)
    assert name1 == "topic_current_state_1"

    # Compound with stopwords should filter stopwords out
    name2 = MultipassDreamReasoner._entity_name(
        "and the deployment guide",
        ReasoningTaskKind.DURABLE_LESSON,
        1,
    )
    assert name2 == "deployment_guide_durable_lesson_2"


def test_gate_rejects_duplicate_candidates_in_same_run() -> None:
    gate = DreamEvidenceGate()
    now = datetime(2026, 9, 4, 2, 0, tzinfo=UTC)
    evidence = [
        EvidenceItem(
            id="11111111-1111-4111-8111-111111111111",
            record_type="knowledge",
            content="Evidence 1",
            metadata={"domain": "ops", "topic": "deploy", "verification": "tested"},
            score=0.9,
            event_time=now,
        )
    ]
    request = DreamReasoningRequest(
        request_id="req-dup",
        session_id="s-dup",
        focal_topics=["deploy"],
        session_start=now,
        session_end=now,
        evidence_by_topic={"deploy": evidence},
    )
    result = DreamReasoningResult(
        request_id="req-dup",
        candidates=[
            DreamCandidate(
                entity_name="deploy_fact_1",
                entity_type="fact",
                summary="Deployment procedure completed successfully.",
                content="Deployment procedure completed successfully.",
                evidence_ids=["11111111-1111-4111-8111-111111111111"],
                confidence=0.9,
                classification="new_knowledge",
                context={"topic": "deploy"},
            ),
            # Near-identical second candidate
            DreamCandidate(
                entity_name="deploy_fact_2",
                entity_type="fact",
                summary="  deployment procedure completed successfully.  ",
                content="Deployment procedure completed successfully.",
                evidence_ids=["11111111-1111-4111-8111-111111111111"],
                confidence=0.9,
                classification="new_knowledge",
                context={"topic": "deploy"},
            ),
        ],
    )

    eval_result = gate.evaluate(request, result)
    assert len(eval_result.candidates) == 2
    # First candidate is evaluated normally
    assert eval_result.candidates[0].decision in {
        PromotionDecision.PROMOTE,
        PromotionDecision.REVIEW,
    }
    # Second duplicate candidate is rejected deterministically
    assert eval_result.candidates[1].decision == PromotionDecision.REJECT
    assert "duplicate_candidate_in_run" in eval_result.candidates[1].reasons


def test_pending_reviews_filters_by_project(tmp_path) -> None:
    audit = DreamRunAuditStore(tmp_path / "audit.sqlite")
    queue = DreamQueue(tmp_path / "queue.sqlite")
    operations = DreamOperations(queue=queue, audit=audit)

    now = datetime(2026, 9, 4, 2, 0, tzinfo=UTC)
    request = DreamReasoningRequest(
        request_id="req-proj",
        session_id="s-proj",
        focal_topics=["code"],
        session_start=now,
        session_end=now,
        evidence_by_topic={"code": []},
    )
    audit.start(dream_run_id="run-proj", request=request)

    cand_cyber = DreamCandidate(
        entity_name="cb_1",
        entity_type="fact",
        summary="CyberBrain summary",
        content="CyberBrain content",
        evidence_ids=[],
        confidence=0.7,
        classification="new_knowledge",
        context={"project": "CyberBrain"},
    )
    cand_other = DreamCandidate(
        entity_name="other_1",
        entity_type="fact",
        summary="Other summary",
        content="Other content",
        evidence_ids=[],
        confidence=0.7,
        classification="new_knowledge",
        context={"project": "CDT_Engineer"},
    )

    with audit._connect() as conn:
        conn.execute(
            """
            INSERT INTO dream_candidate_decisions (
                dream_run_id, candidate_index, candidate_json, decision,
                reasoner_confidence, evidence_strength, promotion_confidence,
                evidence_ids_json, reasons_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-proj",
                0,
                json.dumps(cand_cyber.__dict__),
                "review",
                0.7,
                0.5,
                0.6,
                "[]",
                "[\"test\"]",
                now.isoformat(),
            ),
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
                "run-proj",
                1,
                json.dumps(cand_other.__dict__),
                "review",
                0.7,
                0.5,
                0.6,
                "[]",
                "[\"test\"]",
                now.isoformat(),
            ),
        )

    # All pending reviews
    all_reviews = operations.pending_reviews(limit=10)
    assert len(all_reviews) == 2

    # Scoped to CyberBrain
    cb_reviews = operations.pending_reviews(limit=10, project="CyberBrain")
    assert len(cb_reviews) == 1
    assert cb_reviews[0]["candidate"]["entity_name"] == "cb_1"

    # Scoped to CDT_Engineer
    cdt_reviews = operations.pending_reviews(limit=10, project="CDT_Engineer")
    assert len(cdt_reviews) == 1
    assert cdt_reviews[0]["candidate"]["entity_name"] == "other_1"
