# SPDX-License-Identifier: MPL-2.0
"""Immutable M6 Agent Self-Model domain contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from cyberbrain.schemas.models import IdentityTrust
from cyberbrain.tenancy import normalize_identifier

SELF_MODEL_VERSION = "self-model-v2"


class SelfModelHypothesisKind(StrEnum):
    CAPABILITY = "capability"
    LIMITATION = "limitation"
    WORKFLOW_TENDENCY = "workflow_tendency"
    STRATEGY_CONSTRAINT = "strategy_constraint"
    UNCERTAIN_CAPABILITY = "uncertain_capability"


class SelfModelReviewStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class SelfModelEvidenceDiversity:
    distinct_sessions: int
    distinct_projects: int
    distinct_topics: int

    def __post_init__(self) -> None:
        for name in ("distinct_sessions", "distinct_projects", "distinct_topics"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"self-model {name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class SelfModelEvidenceSample:
    """One resolved prospective outcome eligible for Self-Model analysis."""

    prediction_id: str
    outcome_id: str
    agent_id: str
    session_id: str
    project: str | None
    topic: str | None
    assessment: str
    prediction_confidence: float
    prediction_error: float | None
    identity_trust: IdentityTrust
    strategy_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("prediction_id", "outcome_id", "session_id", "assessment"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"self-model evidence {name} must not be empty")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "agent_id", normalize_identifier(self.agent_id))
        object.__setattr__(self, "identity_trust", IdentityTrust(self.identity_trust))
        confidence = float(self.prediction_confidence)
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("self-model evidence prediction_confidence must be within [0, 1]")
        object.__setattr__(self, "prediction_confidence", confidence)
        if self.prediction_error is not None:
            error = float(self.prediction_error)
            if not math.isfinite(error) or not 0 <= error <= 1:
                raise ValueError("self-model evidence prediction_error must be within [0, 1]")
            object.__setattr__(self, "prediction_error", error)
        tags = tuple(sorted({tag.strip() for tag in self.strategy_tags if tag.strip()}))
        object.__setattr__(self, "strategy_tags", tags)

    @property
    def evidence_ids(self) -> tuple[str, str]:
        return (self.prediction_id, self.outcome_id)

    @property
    def trusted(self) -> bool:
        return self.identity_trust is IdentityTrust.AUTHENTICATED


@dataclass(frozen=True, slots=True)
class SelfModelHypothesis:
    """Revisable hypothesis with no authority until explicitly accepted."""

    hypothesis_id: str
    agent_id: str
    kind: SelfModelHypothesisKind
    claim: str
    support_evidence_ids: tuple[str, ...]
    counterexample_evidence_ids: tuple[str, ...]
    confidence: float
    sample_count: int
    diversity: SelfModelEvidenceDiversity
    generated_at: datetime
    reason_codes: tuple[str, ...]
    scope_topic: str | None = None
    review_status: SelfModelReviewStatus = SelfModelReviewStatus.PENDING
    reviewed_at: datetime | None = None
    version: str = SELF_MODEL_VERSION

    def __post_init__(self) -> None:
        hypothesis_id = self.hypothesis_id.strip()
        claim = self.claim.strip()
        if not hypothesis_id:
            raise ValueError("self-model hypothesis_id must not be empty")
        if not claim:
            raise ValueError("self-model claim must not be empty")
        object.__setattr__(self, "hypothesis_id", hypothesis_id)
        object.__setattr__(self, "agent_id", normalize_identifier(self.agent_id))
        object.__setattr__(self, "kind", SelfModelHypothesisKind(self.kind))
        object.__setattr__(self, "review_status", SelfModelReviewStatus(self.review_status))
        object.__setattr__(self, "claim", claim)
        if self.scope_topic is not None:
            cleaned_topic = self.scope_topic.strip()
            object.__setattr__(self, "scope_topic", cleaned_topic or None)

        if isinstance(self.confidence, bool) or not isinstance(self.confidence, int | float):
            raise ValueError("self-model confidence must be a finite number")
        confidence = float(self.confidence)
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("self-model confidence must be within [0, 1]")
        object.__setattr__(self, "confidence", confidence)

        if isinstance(self.sample_count, bool) or not isinstance(self.sample_count, int):
            raise ValueError("self-model sample_count must be an integer")
        if self.sample_count < 1:
            raise ValueError("self-model sample_count must be positive")

        support = tuple(item.strip() for item in self.support_evidence_ids if item.strip())
        counterexamples = tuple(
            item.strip() for item in self.counterexample_evidence_ids if item.strip()
        )
        if not support:
            raise ValueError("self-model hypothesis requires supporting evidence IDs")
        if len(support) != len(set(support)):
            raise ValueError("self-model supporting evidence IDs must be unique")
        if len(counterexamples) != len(set(counterexamples)):
            raise ValueError("self-model counterexample evidence IDs must be unique")
        if set(support) & set(counterexamples):
            raise ValueError("self-model support and counterexample evidence must not overlap")
        object.__setattr__(self, "support_evidence_ids", support)
        object.__setattr__(self, "counterexample_evidence_ids", counterexamples)

        for name in ("generated_at", "reviewed_at"):
            value = getattr(self, name)
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"self-model {name} must include a timezone")
        if self.review_status is SelfModelReviewStatus.PENDING and self.reviewed_at is not None:
            raise ValueError("pending self-model hypothesis cannot have reviewed_at")
        if self.review_status is not SelfModelReviewStatus.PENDING and self.reviewed_at is None:
            raise ValueError("reviewed self-model hypothesis requires reviewed_at")

        reasons = tuple(code.strip() for code in self.reason_codes if code.strip())
        if not reasons:
            raise ValueError("self-model hypothesis requires reason codes")
        if len(reasons) != len(set(reasons)):
            raise ValueError("self-model reason codes must be unique")
        object.__setattr__(self, "reason_codes", reasons)

    @property
    def accepted(self) -> bool:
        return self.review_status is SelfModelReviewStatus.ACCEPTED

    def reviewed(
        self, *, status: SelfModelReviewStatus, reviewed_at: datetime
    ) -> SelfModelHypothesis:
        status = SelfModelReviewStatus(status)
        if status is SelfModelReviewStatus.PENDING:
            raise ValueError("review decision cannot remain pending")
        return replace(self, review_status=status, reviewed_at=reviewed_at)
