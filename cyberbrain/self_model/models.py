# SPDX-License-Identifier: MPL-2.0
"""Immutable M6 Agent Self-Model domain contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from cyberbrain.tenancy import normalize_identifier

SELF_MODEL_VERSION = "self-model-v1"


class SelfModelHypothesisKind(StrEnum):
    CAPABILITY = "capability"
    LIMITATION = "limitation"
    WORKFLOW_TENDENCY = "workflow_tendency"
    STRATEGY_CONSTRAINT = "strategy_constraint"
    UNCERTAIN_CAPABILITY = "uncertain_capability"


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
class SelfModelHypothesis:
    """Read-only, revisable hypothesis contract. This type grants no behavioral authority."""

    hypothesis_id: str
    agent_id: str
    kind: SelfModelHypothesisKind
    claim: str
    support_evidence_ids: tuple[str, ...]
    counterexample_evidence_ids: tuple[str, ...]
    confidence: float
    sample_count: int
    diversity: SelfModelEvidenceDiversity
    reviewed_at: datetime
    reason_codes: tuple[str, ...]
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
        object.__setattr__(self, "claim", claim)

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

        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("self-model reviewed_at must include a timezone")
        reasons = tuple(code.strip() for code in self.reason_codes if code.strip())
        if not reasons:
            raise ValueError("self-model hypothesis requires reason codes")
        if len(reasons) != len(set(reasons)):
            raise ValueError("self-model reason codes must be unique")
        object.__setattr__(self, "reason_codes", reasons)
