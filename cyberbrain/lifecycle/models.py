# SPDX-License-Identifier: MPL-2.0
"""Immutable M7 Memory Lifecycle contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from cyberbrain.schemas.models import LifecycleState, RetentionDirective

LIFECYCLE_VERSION = "memory-lifecycle-v1"


class LifecycleDecisionKind(StrEnum):
    KEEP_ACTIVE = "keep_active"
    SUPPRESS = "suppress"
    REMAIN_SUPPRESSED = "remain_suppressed"
    REACTIVATE = "reactivate"


class LifecycleReasonCode(StrEnum):
    EXPLICIT_KEEP = "explicit_keep"
    RECENT = "recent"
    FREQUENTLY_ACCESSED = "frequently_accessed"
    HIGH_SALIENCE = "high_salience"
    CONCEPT_LINKED = "concept_linked"
    UNRESOLVED = "unresolved"
    EXPLICIT_RELEVANCE = "explicit_relevance"
    STALE = "stale"
    NEVER_ACCESSED = "never_accessed"
    SUPERSEDED_OR_CONTRADICTED = "superseded_or_contradicted"
    STORAGE_PRESSURE = "storage_pressure"
    BELOW_SUPPRESSION_THRESHOLD = "below_suppression_threshold"
    ABOVE_REACTIVATION_THRESHOLD = "above_reactivation_threshold"


@dataclass(frozen=True, slots=True)
class LifecycleSignals:
    record_id: str
    lifecycle_state: LifecycleState
    retention_directive: RetentionDirective
    age_days: float
    access_count: int
    days_since_last_access: float | None
    salience_score: float
    superseded_or_contradicted: bool = False
    concept_linked: bool = False
    unresolved: bool = False
    storage_pressure: float = 0.0
    explicit_relevance: bool = False

    def __post_init__(self) -> None:
        record_id = self.record_id.strip()
        if not record_id:
            raise ValueError("lifecycle record_id must not be empty")
        object.__setattr__(self, "record_id", record_id)
        object.__setattr__(self, "lifecycle_state", LifecycleState(self.lifecycle_state))
        object.__setattr__(
            self, "retention_directive", RetentionDirective(self.retention_directive)
        )
        for name in ("age_days", "salience_score", "storage_pressure"):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise ValueError(f"lifecycle {name} must be finite")
            object.__setattr__(self, name, value)
        if self.age_days < 0:
            raise ValueError("lifecycle age_days must not be negative")
        if not 0 <= self.salience_score <= 1:
            raise ValueError("lifecycle salience_score must be within [0, 1]")
        if not 0 <= self.storage_pressure <= 1:
            raise ValueError("lifecycle storage_pressure must be within [0, 1]")
        if isinstance(self.access_count, bool) or not isinstance(self.access_count, int):
            raise ValueError("lifecycle access_count must be an integer")
        if self.access_count < 0:
            raise ValueError("lifecycle access_count must not be negative")
        if self.days_since_last_access is not None:
            value = float(self.days_since_last_access)
            if not math.isfinite(value) or value < 0:
                raise ValueError("lifecycle days_since_last_access must be non-negative")
            object.__setattr__(self, "days_since_last_access", value)


@dataclass(frozen=True, slots=True)
class LifecyclePolicy:
    suppression_threshold: float = 0.35
    reactivation_threshold: float = 0.65
    recent_days: float = 30.0
    stale_days: float = 180.0
    frequent_access_count: int = 8

    def __post_init__(self) -> None:
        if not 0 < self.suppression_threshold < self.reactivation_threshold < 1:
            raise ValueError("lifecycle thresholds must satisfy 0 < suppress < reactivate < 1")
        if self.recent_days <= 0 or self.stale_days <= self.recent_days:
            raise ValueError("lifecycle stale_days must exceed recent_days")
        if self.frequent_access_count < 1:
            raise ValueError("lifecycle frequent_access_count must be positive")


@dataclass(frozen=True, slots=True)
class LifecycleDecision:
    record_id: str
    decision: LifecycleDecisionKind
    retention_score: float
    reason_codes: tuple[LifecycleReasonCode, ...]
    version: str = LIFECYCLE_VERSION

    def __post_init__(self) -> None:
        score = float(self.retention_score)
        if not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("lifecycle retention_score must be within [0, 1]")
        object.__setattr__(self, "retention_score", score)
        if not self.reason_codes:
            raise ValueError("lifecycle decision requires reason codes")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("lifecycle decision reason codes must be unique")
