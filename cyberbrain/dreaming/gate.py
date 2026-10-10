# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
import re
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
    minimum_evidence_count: int = 2
    near_duplicate_jaccard: float = 0.72
    near_duplicate_min_tokens: int = 5
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
            item.id: item for items in request.evidence_by_topic.values() for item in items
        }
        seen_fingerprints: dict[str, int] = {}
        kept_signatures: dict[int, tuple[str, str, str, bool, str, str]] = {}
        kept_tokens: dict[int, frozenset[str]] = {}
        decisions: list[CandidateGateResult] = []
        for index, candidate in enumerate(result.candidates):
            fp = self._candidate_fingerprint(candidate, evidence_by_id)
            if fp in seen_fingerprints:
                first_idx = seen_fingerprints[fp]
                first_candidate = result.candidates[first_idx]
                merged_ids = list(
                    dict.fromkeys(first_candidate.evidence_ids + list(candidate.evidence_ids))
                )
                merged_candidate = DreamCandidate(
                    entity_name=first_candidate.entity_name,
                    entity_type=first_candidate.entity_type,
                    summary=first_candidate.summary,
                    content=first_candidate.content,
                    evidence_ids=merged_ids,
                    confidence=max(first_candidate.confidence, candidate.confidence),
                    classification=first_candidate.classification,
                    negative_knowledge=first_candidate.negative_knowledge,
                    context=dict(first_candidate.context),
                )
                result.candidates[first_idx] = merged_candidate

                reevaluated = self._evaluate_candidate(first_idx, merged_candidate, evidence_by_id)
                reasons = list(reevaluated.reasons)
                if "evidence_merged_from_duplicate" not in reasons:
                    reasons.append("evidence_merged_from_duplicate")

                decisions[first_idx] = CandidateGateResult(
                    candidate_index=first_idx,
                    decision=reevaluated.decision,
                    reasoner_confidence=reevaluated.reasoner_confidence,
                    evidence_strength=reevaluated.evidence_strength,
                    promotion_confidence=reevaluated.promotion_confidence,
                    evidence_ids=merged_ids,
                    reasons=reasons,
                )
                decisions.append(
                    self._result(
                        index,
                        candidate,
                        PromotionDecision.REJECT,
                        0.0,
                        0.0,
                        ["duplicate_candidate_in_run", f"merged_into_index_{first_idx}"],
                    )
                )
                continue
            near_idx = self._near_duplicate_index(
                candidate,
                evidence_by_id,
                kept_signatures,
                kept_tokens,
            )
            if near_idx is not None:
                first_candidate = result.candidates[near_idx]
                merged_ids = list(
                    dict.fromkeys(first_candidate.evidence_ids + list(candidate.evidence_ids))
                )
                merged_candidate = DreamCandidate(
                    entity_name=first_candidate.entity_name,
                    entity_type=first_candidate.entity_type,
                    summary=first_candidate.summary,
                    content=first_candidate.content,
                    evidence_ids=merged_ids,
                    confidence=max(first_candidate.confidence, candidate.confidence),
                    classification=first_candidate.classification,
                    negative_knowledge=first_candidate.negative_knowledge,
                    context=dict(first_candidate.context),
                )
                result.candidates[near_idx] = merged_candidate

                reevaluated = self._evaluate_candidate(near_idx, merged_candidate, evidence_by_id)
                reasons = list(reevaluated.reasons)
                if "evidence_merged_from_near_duplicate" not in reasons:
                    reasons.append("evidence_merged_from_near_duplicate")

                decisions[near_idx] = CandidateGateResult(
                    candidate_index=near_idx,
                    decision=reevaluated.decision,
                    reasoner_confidence=reevaluated.reasoner_confidence,
                    evidence_strength=reevaluated.evidence_strength,
                    promotion_confidence=reevaluated.promotion_confidence,
                    evidence_ids=merged_ids,
                    reasons=reasons,
                )
                decisions.append(
                    self._result(
                        index,
                        candidate,
                        PromotionDecision.REJECT,
                        0.0,
                        0.0,
                        ["duplicate_candidate_in_run", f"merged_into_index_{near_idx}"],
                    )
                )
                continue
            seen_fingerprints[fp] = index
            kept_signatures[index], kept_tokens[index] = self._near_duplicate_signature(
                candidate, evidence_by_id
            )
            decisions.append(self._evaluate_candidate(index, candidate, evidence_by_id))
        return DreamGateResult(request_id=request.request_id, candidates=decisions)

    @staticmethod
    def _candidate_fingerprint(
        candidate: DreamCandidate,
        evidence_by_id: dict[str, EvidenceItem],
    ) -> str:
        content_norm = re.sub(
            r"\s+", " ", (candidate.content or candidate.summary or "").casefold().strip()
        )
        # Execution labels differ across passes; semantic context and polarity must agree.
        context = {
            key: value
            for key, value in candidate.context.items()
            if key not in {"task_id", "reasoning_section"}
        }
        partitions = set()
        unknown = []
        for evidence_id in candidate.evidence_ids:
            item = evidence_by_id.get(evidence_id)
            if item is None:
                unknown.append(evidence_id)
                continue
            metadata = item.metadata
            evidence_context = metadata.get("context") or {}
            domain = metadata.get("domain")
            if domain is None and isinstance(evidence_context, dict):
                domain = evidence_context.get("legacy_domain") or evidence_context.get("domain")
            partitions.add(
                json.dumps(
                    [metadata.get(key) for key in ("tenant", "user", "agent", "project")]
                    + [domain],
                    sort_keys=True,
                    ensure_ascii=False,
                )
            )
        return json.dumps(
            [
                content_norm,
                candidate.entity_type.casefold().strip(),
                candidate.classification.casefold().strip(),
                candidate.negative_knowledge,
                context,
                sorted(partitions),
                sorted(set(unknown)),
            ],
            sort_keys=True,
            ensure_ascii=False,
        )

    def _near_duplicate_signature(
        self,
        candidate: DreamCandidate,
        evidence_by_id: dict[str, EvidenceItem],
    ) -> tuple[tuple[str, str, str, bool, str, str], frozenset[str]]:
        text = (candidate.content or candidate.summary or "").casefold().strip()
        tokens = frozenset(re.findall(r"[a-z0-9]+", text))
        context = {
            key: value
            for key, value in candidate.context.items()
            if key not in {"task_id", "reasoning_section"}
        }
        partitions: list[str] = []
        unknown: list[str] = []
        for evidence_id in candidate.evidence_ids:
            item = evidence_by_id.get(evidence_id)
            if item is None:
                unknown.append(evidence_id)
                continue
            metadata = item.metadata
            evidence_context = metadata.get("context") or {}
            domain = metadata.get("domain")
            if domain is None and isinstance(evidence_context, dict):
                domain = evidence_context.get("legacy_domain") or evidence_context.get("domain")
            partitions.append(
                json.dumps(
                    [metadata.get(key) for key in ("tenant", "user", "agent", "project")]
                    + [domain],
                    sort_keys=True,
                    ensure_ascii=False,
                )
            )
        signature = (
            candidate.entity_type.casefold().strip(),
            candidate.classification.casefold().strip(),
            json.dumps(context, sort_keys=True, ensure_ascii=False),
            bool(candidate.negative_knowledge),
            json.dumps(sorted(partitions), ensure_ascii=False),
            json.dumps(sorted(set(unknown)), ensure_ascii=False),
        )
        return signature, tokens

    def _near_duplicate_index(
        self,
        candidate: DreamCandidate,
        evidence_by_id: dict[str, EvidenceItem],
        kept_signatures: dict[int, tuple[str, str, str, bool, str, str]],
        kept_tokens: dict[int, frozenset[str]],
    ) -> int | None:
        signature, tokens = self._near_duplicate_signature(candidate, evidence_by_id)
        if len(tokens) < self._policy.near_duplicate_min_tokens:
            return None
        for index, kept_signature in kept_signatures.items():
            if kept_signature != signature:
                continue
            kept = kept_tokens[index]
            if len(kept) < self._policy.near_duplicate_min_tokens:
                continue
            union = tokens | kept
            if not union:
                continue
            jaccard = len(tokens & kept) / len(union)
            if jaccard >= self._policy.near_duplicate_jaccard:
                return index
        return None

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
