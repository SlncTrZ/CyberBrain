# SPDX-License-Identifier: MPL-2.0
"""Immutable domain models for evidence-backed concept formation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

CONCEPT_CANDIDATE_VERSION = "concept-candidate-v1"


class ConceptEvidenceType(StrEnum):
    KNOWLEDGE = "knowledge"
    EPISODE = "episode"


class ConceptReasonCode(StrEnum):
    RECURRING_TOPIC = "recurring_topic"
    BROAD_SUPPORT = "broad_support"
    MULTI_SESSION_SUPPORT = "multi_session_support"
    MULTI_SOURCE_SUPPORT = "multi_source_support"
    MIXED_RECORD_TYPES = "mixed_record_types"
    ENTITY_DIVERSITY = "entity_diversity"
    STRONG_VERIFICATION_PRESENT = "strong_verification_present"
    COUNTEREXAMPLES_PRESENT = "counterexamples_present"


@dataclass(frozen=True, slots=True)
class ConceptEvidence:
    """Metadata-only evidence reference supplied after authorization/eligibility."""

    evidence_id: str
    record_type: ConceptEvidenceType
    scope_marker: str
    domain: str
    topic: str
    project: str | None = None
    entity_type: str | None = None
    entity_name: str | None = None
    session_id: str | None = None
    source: str | None = None
    verification: str | None = None
    counterexample: bool = False

    def __post_init__(self) -> None:
        for name in ("evidence_id", "scope_marker", "domain", "topic"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"concept {name} must not be empty")
            object.__setattr__(self, name, value)
        for name in (
            "project",
            "entity_type",
            "entity_name",
            "session_id",
            "source",
            "verification",
        ):
            value = getattr(self, name)
            if value is None:
                continue
            normalized = str(value).strip()
            object.__setattr__(self, name, normalized or None)


@dataclass(frozen=True, slots=True)
class ConceptDiscoveryPolicy:
    minimum_support_count: int = 2
    minimum_knowledge_only_support_count: int = 5
    minimum_episode_or_mixed_support_count: int = 3
    minimum_distinct_entities: int = 2
    minimum_distinct_sessions: int = 2
    broad_support_count: int = 5
    generic_topics: tuple[str, ...] = (
        "chat_history",
        "legacy_source_chunk",
        "general",
        "unknown",
    )
    strong_verifications: tuple[str, ...] = (
        "user_confirmed",
        "tested",
        "observed",
    )

    def __post_init__(self) -> None:
        if self.minimum_support_count < 2:
            raise ValueError("minimum_support_count must be >= 2")
        if self.minimum_knowledge_only_support_count < self.minimum_support_count:
            raise ValueError(
                "minimum_knowledge_only_support_count must be >= minimum_support_count"
            )
        if self.minimum_episode_or_mixed_support_count < self.minimum_support_count:
            raise ValueError(
                "minimum_episode_or_mixed_support_count must be >= minimum_support_count"
            )
        if self.minimum_distinct_entities < 1:
            raise ValueError("minimum_distinct_entities must be >= 1")
        if self.minimum_distinct_sessions < 1:
            raise ValueError("minimum_distinct_sessions must be >= 1")
        if self.broad_support_count < self.minimum_support_count:
            raise ValueError("broad_support_count must be >= minimum_support_count")
        normalized_topics = tuple(
            sorted({item.strip().casefold() for item in self.generic_topics if item.strip()})
        )
        object.__setattr__(self, "generic_topics", normalized_topics)
        normalized_verifications = tuple(
            sorted(
                {
                    item.strip().casefold()
                    for item in self.strong_verifications
                    if item.strip()
                }
            )
        )
        object.__setattr__(self, "strong_verifications", normalized_verifications)


@dataclass(frozen=True, slots=True)
class ConceptCandidate:
    candidate_concept_id: str
    scope_marker: str
    domain: str
    topic: str
    label: str
    summary_candidate: str | None
    project: str | None
    supporting_evidence_ids: tuple[str, ...]
    counterexample_ids: tuple[str, ...]
    distinct_session_count: int
    distinct_source_count: int
    distinct_entity_count: int
    record_types: tuple[ConceptEvidenceType, ...]
    strong_verification_count: int
    formation_confidence: float
    reason_codes: tuple[ConceptReasonCode, ...]
    support_fingerprint: str
    candidate_version: str = CONCEPT_CANDIDATE_VERSION

    def __post_init__(self) -> None:
        if not self.candidate_concept_id.strip():
            raise ValueError("candidate_concept_id must not be empty")
        if not self.scope_marker.strip():
            raise ValueError("concept scope_marker must not be empty")
        if not self.domain.strip() or not self.topic.strip() or not self.label.strip():
            raise ValueError("concept domain/topic/label must not be empty")
        if len(set(self.supporting_evidence_ids)) != len(self.supporting_evidence_ids):
            raise ValueError("supporting evidence IDs must be unique")
        if len(set(self.counterexample_ids)) != len(self.counterexample_ids):
            raise ValueError("counterexample IDs must be unique")
        if set(self.supporting_evidence_ids) & set(self.counterexample_ids):
            raise ValueError("supporting and counterexample evidence must be disjoint")
        if not self.supporting_evidence_ids:
            raise ValueError("concept candidate requires supporting evidence")
        for name in (
            "distinct_session_count",
            "distinct_source_count",
            "distinct_entity_count",
            "strong_verification_count",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0")
        if not math.isfinite(self.formation_confidence) or not 0 <= self.formation_confidence <= 1:
            raise ValueError("formation_confidence must be finite and within [0, 1]")
        if not self.support_fingerprint.strip():
            raise ValueError("support_fingerprint must not be empty")
