# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime

from cyberbrain.dreaming.audit import DreamRunAuditStore
from cyberbrain.dreaming.gate import CandidateGateResult, DreamGateResult, PromotionDecision
from cyberbrain.dreaming.reasoner import (
    DreamCandidate,
    DreamReasoningRequest,
    DreamReasoningResult,
    EvidenceItem,
)
from cyberbrain.dreaming.review import DreamReviewResolver


def _request() -> DreamReasoningRequest:
    now = datetime(2026, 9, 4, 2, 0, tzinfo=UTC)
    return DreamReasoningRequest(
        request_id="req-review",
        session_id="session-review",
        focal_topics=["CyberBrain"],
        session_start=now,
        session_end=now,
        evidence_by_topic={
            "CyberBrain": [
                EvidenceItem(
                    id="11111111-1111-4111-8111-111111111111",
                    record_type="knowledge",
                    content="evidence",
                    score=0.8,
                    event_time=now,
                    metadata={"verification": "unverified"},
                )
            ]
        },
    )


def _result() -> DreamReasoningResult:
    return DreamReasoningResult(
        request_id="req-review",
        candidates=[
            DreamCandidate(
                entity_name="candidate",
                entity_type="lesson",
                summary="summary",
                content="candidate",
                evidence_ids=["11111111-1111-4111-8111-111111111111"],
                confidence=0.7,
                classification="context_dependent",
            )
        ],
    )


def _gate() -> DreamGateResult:
    return DreamGateResult(
        request_id="req-review",
        candidates=[
            CandidateGateResult(
                candidate_index=0,
                decision=PromotionDecision.REVIEW,
                reasoner_confidence=0.7,
                evidence_strength=0.4,
                promotion_confidence=0.5,
                evidence_ids=["11111111-1111-4111-8111-111111111111"],
                reasons=["context_dependent_requires_review"],
            )
        ],
    )


def _prepare_store(tmp_path) -> DreamRunAuditStore:
    store = DreamRunAuditStore(tmp_path / "dreaming.sqlite")
    store.start(dream_run_id="dream-run-review", request=_request())
    store.complete(
        dream_run_id="dream-run-review",
        result=_result(),
        gate=_gate(),
    )
    return store


def test_pending_review_can_be_approved_and_applied(tmp_path) -> None:
    store = _prepare_store(tmp_path)

    pending = store.pending_reviews()
    assert len(pending) == 1
    assert pending[0]["candidate_index"] == 0

    store.resolve_review(
        dream_run_id="dream-run-review",
        candidate_index=0,
        resolution="approved",
        reviewer="human:test",
        reason="evidence inspected",
    )

    assert store.pending_reviews() == []
    resolved = DreamReviewResolver(store).apply(
        dream_run_id="dream-run-review",
        gate=_gate(),
    )
    assert resolved.candidates[0].decision == PromotionDecision.PROMOTE
    assert "human_review_approved" in resolved.candidates[0].reasons


def test_review_rejection_becomes_reject_without_mutating_original_gate(tmp_path) -> None:
    store = _prepare_store(tmp_path)
    original = _gate()

    store.resolve_review(
        dream_run_id="dream-run-review",
        candidate_index=0,
        resolution="rejected",
        reviewer="human:test",
    )
    resolved = DreamReviewResolver(store).apply(
        dream_run_id="dream-run-review",
        gate=original,
    )

    assert original.candidates[0].decision == PromotionDecision.REVIEW
    assert resolved.candidates[0].decision == PromotionDecision.REJECT
    assert "human_review_rejected" in resolved.candidates[0].reasons
