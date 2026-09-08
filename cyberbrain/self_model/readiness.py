# SPDX-License-Identifier: MPL-2.0
"""Fail-closed M6 readiness evaluation over prospective outcome evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cyberbrain.tenancy import TrustedIdentityEvidence, normalize_identifier

from .models import SelfModelEvidenceDiversity


class SelfModelReadinessStatus(StrEnum):
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    READY_READ_ONLY = "ready_read_only"


class SelfModelReadinessReason(StrEnum):
    TRUSTED_AGENT_IDENTITY_REQUIRED = "trusted_agent_identity_required"
    TRUSTED_AGENT_IDENTITY_MISMATCH = "trusted_agent_identity_mismatch"
    EVIDENCE_SCAN_INCOMPLETE = "evidence_scan_incomplete"
    OUTCOME_SAMPLE_FLOOR_NOT_MET = "outcome_sample_floor_not_met"
    SESSION_DIVERSITY_NOT_MET = "session_diversity_not_met"
    TOPIC_DIVERSITY_NOT_MET = "topic_diversity_not_met"
    READ_ONLY_READY = "read_only_ready"


@dataclass(frozen=True, slots=True)
class SelfModelReadinessPolicy:
    """Conservative M6.1 entry gate; it does not authorize persistent influence."""

    minimum_resolved_outcomes: int = 20
    minimum_distinct_sessions: int = 3
    minimum_distinct_topics: int = 3

    def __post_init__(self) -> None:
        for name in (
            "minimum_resolved_outcomes",
            "minimum_distinct_sessions",
            "minimum_distinct_topics",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"self-model {name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class SelfModelReadinessInput:
    agent_id: str
    trusted_identity: TrustedIdentityEvidence | None
    resolved_outcomes: int
    diversity: SelfModelEvidenceDiversity
    evidence_ids: tuple[str, ...]
    may_be_incomplete: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_id", normalize_identifier(self.agent_id))
        if isinstance(self.resolved_outcomes, bool) or not isinstance(self.resolved_outcomes, int):
            raise ValueError("self-model resolved_outcomes must be an integer")
        if self.resolved_outcomes < 0:
            raise ValueError("self-model resolved_outcomes must not be negative")
        evidence_ids = tuple(item.strip() for item in self.evidence_ids if item.strip())
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("self-model readiness evidence IDs must be unique")
        if self.resolved_outcomes > 0 and not evidence_ids:
            raise ValueError("self-model readiness requires evidence IDs for resolved outcomes")
        object.__setattr__(self, "evidence_ids", evidence_ids)


@dataclass(frozen=True, slots=True)
class SelfModelReadinessReport:
    agent_id: str
    status: SelfModelReadinessStatus
    reasons: tuple[SelfModelReadinessReason, ...]
    resolved_outcomes: int
    minimum_resolved_outcomes: int
    diversity: SelfModelEvidenceDiversity
    minimum_distinct_sessions: int
    minimum_distinct_topics: int
    evidence_ids: tuple[str, ...]
    trusted_identity_source: str | None

    @property
    def ready(self) -> bool:
        return self.status is SelfModelReadinessStatus.READY_READ_ONLY


class SelfModelReadinessEvaluator:
    """Gate M6.1 without generating or persisting any self-model hypothesis."""

    def __init__(self, policy: SelfModelReadinessPolicy | None = None) -> None:
        self._policy = policy or SelfModelReadinessPolicy()

    def evaluate(self, evidence: SelfModelReadinessInput) -> SelfModelReadinessReport:
        reasons: list[SelfModelReadinessReason] = []
        trusted_source: str | None = None
        identity = evidence.trusted_identity
        if identity is None:
            reasons.append(SelfModelReadinessReason.TRUSTED_AGENT_IDENTITY_REQUIRED)
        else:
            trusted_source = identity.authentication_source
            trusted_agents = identity.scope.agent
            if trusted_agents != frozenset({evidence.agent_id}):
                reasons.append(SelfModelReadinessReason.TRUSTED_AGENT_IDENTITY_MISMATCH)

        if evidence.may_be_incomplete:
            reasons.append(SelfModelReadinessReason.EVIDENCE_SCAN_INCOMPLETE)
        if evidence.resolved_outcomes < self._policy.minimum_resolved_outcomes:
            reasons.append(SelfModelReadinessReason.OUTCOME_SAMPLE_FLOOR_NOT_MET)
        if evidence.diversity.distinct_sessions < self._policy.minimum_distinct_sessions:
            reasons.append(SelfModelReadinessReason.SESSION_DIVERSITY_NOT_MET)
        if evidence.diversity.distinct_topics < self._policy.minimum_distinct_topics:
            reasons.append(SelfModelReadinessReason.TOPIC_DIVERSITY_NOT_MET)

        if reasons:
            status = SelfModelReadinessStatus.INSUFFICIENT_EVIDENCE
        else:
            status = SelfModelReadinessStatus.READY_READ_ONLY
            reasons.append(SelfModelReadinessReason.READ_ONLY_READY)

        return SelfModelReadinessReport(
            agent_id=evidence.agent_id,
            status=status,
            reasons=tuple(reasons),
            resolved_outcomes=evidence.resolved_outcomes,
            minimum_resolved_outcomes=self._policy.minimum_resolved_outcomes,
            diversity=evidence.diversity,
            minimum_distinct_sessions=self._policy.minimum_distinct_sessions,
            minimum_distinct_topics=self._policy.minimum_distinct_topics,
            evidence_ids=evidence.evidence_ids,
            trusted_identity_source=trusted_source,
        )
