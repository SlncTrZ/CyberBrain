# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime

from cyberbrain.dreaming.gate import DreamEvidenceGate, PromotionDecision
from cyberbrain.dreaming.reasoner import (
    DreamCandidate,
    DreamReasoningRequest,
    DreamReasoningResult,
    EvidenceItem,
)


def _request() -> DreamReasoningRequest:
    now = datetime(2026, 9, 4, 2, 0, tzinfo=UTC)
    return DreamReasoningRequest(
        request_id="req-gate",
        session_id="session-1",
        focal_topics=["topic"],
        session_start=now,
        session_end=now,
        evidence_by_topic={
            "topic": [
                EvidenceItem(
                    id="e1",
                    record_type="knowledge",
                    content="tested evidence one",
                    score=0.9,
                    event_time=now,
                    metadata={"verification": "tested"},
                ),
                EvidenceItem(
                    id="e2",
                    record_type="episode",
                    content="observed evidence two",
                    score=0.9,
                    event_time=now,
                    metadata={"verification": "observed"},
                ),
                EvidenceItem(
                    id="e3",
                    record_type="knowledge",
                    content="confirmed evidence three",
                    score=0.9,
                    event_time=now,
                    metadata={"verification": "user_confirmed"},
                ),
                EvidenceItem(
                    id="weak",
                    record_type="knowledge",
                    content="weak evidence",
                    score=0.7,
                    event_time=now,
                    metadata={"verification": "unverified"},
                ),
            ]
        },
    )


def _candidate(*, evidence_ids: list[str], classification: str = "new_knowledge") -> DreamCandidate:
    return DreamCandidate(
        entity_name="candidate",
        entity_type="lesson",
        summary="summary",
        content="durable claim",
        evidence_ids=evidence_ids,
        confidence=0.9,
        classification=classification,
    )


def test_gate_promotes_strong_grounded_candidate() -> None:
    result = DreamReasoningResult(
        request_id="req-gate",
        candidates=[_candidate(evidence_ids=["e1", "e2", "e3"])],
    )
    gate = DreamEvidenceGate().evaluate(_request(), result)

    decision = gate.candidates[0]
    assert decision.decision == PromotionDecision.PROMOTE
    assert decision.evidence_strength > 0.8
    assert decision.promotion_confidence > 0.8


def test_gate_sends_weak_candidate_to_review() -> None:
    result = DreamReasoningResult(
        request_id="req-gate",
        candidates=[_candidate(evidence_ids=["weak"])],
    )
    gate = DreamEvidenceGate().evaluate(_request(), result)

    assert gate.candidates[0].decision == PromotionDecision.REVIEW


def test_gate_rejects_unknown_evidence() -> None:
    result = DreamReasoningResult(
        request_id="req-gate",
        candidates=[_candidate(evidence_ids=["fabricated"])],
    )
    gate = DreamEvidenceGate().evaluate(_request(), result)

    assert gate.candidates[0].decision == PromotionDecision.REJECT
    assert "unknown_evidence_ids" in gate.candidates[0].reasons


def test_gate_forces_context_dependent_to_review() -> None:
    result = DreamReasoningResult(
        request_id="req-gate",
        candidates=[
            _candidate(
                evidence_ids=["e1", "e2", "e3"],
                classification="context_dependent",
            )
        ],
    )
    gate = DreamEvidenceGate().evaluate(_request(), result)

    assert gate.candidates[0].decision == PromotionDecision.REVIEW
