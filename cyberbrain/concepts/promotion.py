# SPDX-License-Identifier: MPL-2.0
"""Evidence gate for future durable M4 concept promotion."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from cyberbrain.knowledge.evolution import EvolutionResult, KnowledgeEvolutionService
from cyberbrain.schemas.models import Verification

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


class ConceptPromotionService:
    """Promotes reviewed and eligible ConceptCandidates into canonical Knowledge."""

    def __init__(
        self,
        *,
        evolution: KnowledgeEvolutionService,
        gate: ConceptPromotionGate | None = None,
    ) -> None:
        self._evolution = evolution
        self._gate = gate or ConceptPromotionGate()

    def promote(
        self,
        candidate: ConceptCandidate,
        *,
        reviewer: str = "operator:concept_review",
        reason: str = "Concept approved after passing promotion gate",
    ) -> EvolutionResult:
        evaluation = self._gate.evaluate(candidate)
        if evaluation.decision != ConceptPromotionDecision.REVIEW:
            raise ValueError(f"Concept candidate cannot be promoted: {evaluation.reasons}")

        entity_name = re.sub(r"[^a-z0-9]+", "_", candidate.label.casefold()).strip("_") or "concept"
        content = (
            f"Concept: {candidate.label}\n\n"
            f"Domain: {candidate.domain}\n"
            f"Topic: {candidate.topic}\n\n"
            f"Abstracted from {len(candidate.supporting_evidence_ids)} supporting evidence items "
            f"with formation confidence {candidate.formation_confidence:.2f}."
        )

        return self._evolution.store(
            content=content,
            summary=f"Abstract concept for {candidate.topic} in {candidate.domain}",
            domain=candidate.domain,
            topic=candidate.topic,
            entity_type="concept",
            entity_name=entity_name,
            project=candidate.project,
            provenance_type="concept_formation",
            verification=Verification.DERIVED,
            confidence=candidate.formation_confidence,
            change_reason=reason,
            context={
                "concept_id": candidate.candidate_concept_id,
                "label": candidate.label,
                "reviewer": reviewer,
            },
        )
