# SPDX-License-Identifier: MPL-2.0
"""Evidence gate for future durable M4 concept promotion."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .models import ConceptCandidate


class ConceptPromotionDecision(StrEnum):
    REVIEW = "review"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ConceptPromotionPolicy:
    minimum_support_count: int = 3
    minimum_formation_confidence: float = 0.45
    minimum_strong_verification_count: int = 1
    require_no_counterexamples: bool = True

    def __post_init__(self) -> None:
        if self.minimum_support_count < 2:
            raise ValueError("minimum_support_count must be >= 2")
        if not 0 <= self.minimum_formation_confidence <= 1:
            raise ValueError("minimum_formation_confidence must be within [0, 1]")
        if self.minimum_strong_verification_count < 0:
            raise ValueError("minimum_strong_verification_count must be >= 0")


@dataclass(frozen=True, slots=True)
class ConceptPromotionEvaluation:
    candidate_concept_id: str
    decision: ConceptPromotionDecision
    reasons: tuple[str, ...]


class ConceptPromotionGate:
    """Never auto-promotes a discovered concept; eligible candidates require review."""

    def __init__(self, policy: ConceptPromotionPolicy | None = None) -> None:
        self._policy = policy or ConceptPromotionPolicy()

    def evaluate(self, candidate: ConceptCandidate) -> ConceptPromotionEvaluation:
        reasons: list[str] = []
        if len(candidate.supporting_evidence_ids) < self._policy.minimum_support_count:
            reasons.append("insufficient_support_count")
        if candidate.formation_confidence < self._policy.minimum_formation_confidence:
            reasons.append("insufficient_formation_confidence")
        if candidate.strong_verification_count < self._policy.minimum_strong_verification_count:
            reasons.append("insufficient_strong_verification")
        if self._policy.require_no_counterexamples and candidate.counterexample_ids:
            reasons.append("counterexamples_require_resolution")

        if reasons:
            return ConceptPromotionEvaluation(
                candidate_concept_id=candidate.candidate_concept_id,
                decision=ConceptPromotionDecision.REJECT,
                reasons=tuple(reasons),
            )
        return ConceptPromotionEvaluation(
            candidate_concept_id=candidate.candidate_concept_id,
            decision=ConceptPromotionDecision.REVIEW,
            reasons=("human_review_required_before_knowledge_evolution",),
        )
