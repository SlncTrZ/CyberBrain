# SPDX-License-Identifier: MPL-2.0
"""Bounded Salience advisory seam for already-authorized candidate sets."""

from __future__ import annotations

from dataclasses import dataclass

from .models import SalienceAssessment, SalienceInput
from .policy import REVIEWED_SALIENCE_POLICY, SALIENCE_POLICY_VERSION
from .scorer import SalienceScorer


class SalienceScopeError(ValueError):
    """Raised when candidates cross an authorization/scope boundary."""


@dataclass(frozen=True, slots=True)
class SalienceCandidate:
    candidate_id: str
    scope_marker: str
    signals: SalienceInput

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("salience candidate_id must not be empty")
        if not self.scope_marker.strip():
            raise ValueError("salience scope_marker must not be empty")


@dataclass(frozen=True, slots=True)
class CandidateSalienceAssessment:
    candidate_id: str
    assessment: SalienceAssessment


@dataclass(frozen=True, slots=True)
class SalienceAdvisory:
    policy_version: str
    assessments: tuple[CandidateSalienceAssessment, ...]
    priority_order: tuple[str, ...]


class SalienceAdvisor:
    """Assess same-scope candidates without mutating or authorizing anything."""

    def __init__(
        self,
        *,
        scorer: SalienceScorer | None = None,
        policy_version: str = SALIENCE_POLICY_VERSION,
    ) -> None:
        self._scorer = scorer or SalienceScorer(REVIEWED_SALIENCE_POLICY)
        normalized_version = policy_version.strip()
        if not normalized_version:
            raise ValueError("salience policy_version must not be empty")
        self._policy_version = normalized_version

    def assess(
        self, candidates: tuple[SalienceCandidate, ...] | list[SalienceCandidate]
    ) -> SalienceAdvisory:
        ordered_candidates = tuple(candidates)
        if not ordered_candidates:
            return SalienceAdvisory(self._policy_version, (), ())

        candidate_ids = [candidate.candidate_id for candidate in ordered_candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("salience candidate IDs must be unique within one advisory set")

        scopes = {candidate.scope_marker for candidate in ordered_candidates}
        if len(scopes) != 1:
            raise SalienceScopeError("salience candidates must share one authorized scope")

        assessments = tuple(
            CandidateSalienceAssessment(
                candidate.candidate_id, self._scorer.assess(candidate.signals)
            )
            for candidate in ordered_candidates
        )
        indexed = list(enumerate(assessments))
        indexed.sort(key=lambda item: (-item[1].assessment.score, item[0]))
        priority_order = tuple(item.candidate_id for _index, item in indexed)
        return SalienceAdvisory(self._policy_version, assessments, priority_order)
