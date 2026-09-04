# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from cyberbrain.dreaming.reasoner import (
    DreamCandidate,
    DreamReasoningRequest,
    DreamReasoningResult,
    EvidenceItem,
)


class PromotionDecision(StrEnum):
    PROMOTE = "promote"
    REVIEW = "review"
    REJECT = "reject"


@dataclass(frozen=True)
class PromotionPolicy:
    promote_threshold: float = 0.78
    review_threshold: float = 0.45
    minimum_evidence_count: int = 1
    strong_verifications: tuple[str, ...] = (
        "user_confirmed",
        "tested",
        "observed",
    )


@dataclass(frozen=True)
class CandidateGateResult:
    candidate_index: int
    decision: PromotionDecision
    reasoner_confidence: float
    evidence_strength: float
    promotion_confidence: float
    evidence_ids: list[str]
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DreamGateResult:
    request_id: str
    candidates: list[CandidateGateResult]


class DreamEvidenceGate:
    def __init__(self, policy: PromotionPolicy | None = None) -> None:
        self._policy = policy or PromotionPolicy()

    def evaluate(
        self,
        request: DreamReasoningRequest,
        result: DreamReasoningResult,
    ) -> DreamGateResult:
        if result.request_id != request.request_id:
            raise ValueError("Dream result request_id does not match request")

        evidence_by_id = {
            item.id: item
            for items in request.evidence_by_topic.values()
            for item in items
        }
        decisions = [
            self._evaluate_candidate(index, candidate, evidence_by_id)
            for index, candidate in enumerate(result.candidates)
        ]
        return DreamGateResult(request_id=request.request_id, candidates=decisions)

    def _evaluate_candidate(
        self,
        index: int,
        candidate: DreamCandidate,
        evidence_by_id: dict[str, EvidenceItem],
    ) -> CandidateGateResult:
        reasons: list[str] = []
        evidence = []
        unknown = []
        for evidence_id in candidate.evidence_ids:
            item = evidence_by_id.get(evidence_id)
            if item is None:
                unknown.append(evidence_id)
            else:
                evidence.append(item)

        if unknown:
            reasons.append("unknown_evidence_ids")
            return self._result(
                index,
                candidate,
                PromotionDecision.REJECT,
                0.0,
                0.0,
                reasons,
            )

        if len(evidence) < self._policy.minimum_evidence_count:
            reasons.append("insufficient_evidence_count")
            return self._result(
                index,
                candidate,
                PromotionDecision.REJECT,
                0.0,
                0.0,
                reasons,
            )

        if candidate.classification == "insufficient_evidence":
            reasons.append("reasoner_classified_insufficient_evidence")
            return self._result(
                index,
                candidate,
                PromotionDecision.REJECT,
                self._evidence_strength(evidence),
                0.0,
                reasons,
            )

        evidence_strength = self._evidence_strength(evidence)
        promotion_confidence = self._promotion_confidence(
            candidate.confidence,
            evidence_strength,
        )

        if candidate.classification in {"contradiction", "true_contradiction"}:
            reasons.append("contradiction_requires_review")
            decision = PromotionDecision.REVIEW
        elif candidate.classification == "context_dependent":
            reasons.append("context_dependent_requires_review")
            decision = PromotionDecision.REVIEW
        elif promotion_confidence >= self._policy.promote_threshold:
            reasons.append("promotion_threshold_met")
            decision = PromotionDecision.PROMOTE
        elif promotion_confidence >= self._policy.review_threshold:
            reasons.append("promotion_confidence_requires_review")
            decision = PromotionDecision.REVIEW
        else:
            reasons.append("promotion_confidence_too_low")
            decision = PromotionDecision.REJECT

        return self._result(
            index,
            candidate,
            decision,
            evidence_strength,
            promotion_confidence,
            reasons,
        )

    def _evidence_strength(self, evidence: list[EvidenceItem]) -> float:
        count_score = min(1.0, len({item.id for item in evidence}) / 3.0)
        verification_score = 0.0
        source_diversity = len({item.record_type for item in evidence})
        diversity_score = min(1.0, source_diversity / 2.0)

        strong = 0
        verified = 0
        for item in evidence:
            verification = str(item.metadata.get("verification") or "").strip().casefold()
            if verification:
                verified += 1
            if verification in self._policy.strong_verifications:
                strong += 1

        if evidence:
            verification_score = (0.7 * strong + 0.3 * verified) / len(evidence)

        score = 0.45 * count_score + 0.4 * verification_score + 0.15 * diversity_score
        return max(0.0, min(1.0, score))

    @staticmethod
    def _promotion_confidence(reasoner_confidence: float, evidence_strength: float) -> float:
        confidence = max(0.0, min(1.0, reasoner_confidence))
        return max(0.0, min(1.0, 0.35 * confidence + 0.65 * evidence_strength))

    @staticmethod
    def _result(
        index: int,
        candidate: DreamCandidate,
        decision: PromotionDecision,
        evidence_strength: float,
        promotion_confidence: float,
        reasons: list[str],
    ) -> CandidateGateResult:
        return CandidateGateResult(
            candidate_index=index,
            decision=decision,
            reasoner_confidence=candidate.confidence,
            evidence_strength=evidence_strength,
            promotion_confidence=promotion_confidence,
            evidence_ids=list(candidate.evidence_ids),
            reasons=list(reasons),
        )
