# SPDX-License-Identifier: MPL-2.0
"""Deterministic M4 concept candidate discovery."""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict

from cyberbrain.salience import SalienceAdvisor, SalienceCandidate, SalienceInput

from .models import (
    ConceptCandidate,
    ConceptDiscoveryPolicy,
    ConceptEvidence,
    ConceptEvidenceType,
    ConceptReasonCode,
)

_NORMALIZE_SPACE = re.compile(r"\s+")


def _normalized_key(value: str) -> str:
    return _NORMALIZE_SPACE.sub(" ", value.strip()).casefold()


def _candidate_id(*, scope_marker: str, domain: str, topic: str) -> str:
    material = "|".join(
        [
            "concept-candidate-v1",
            _normalized_key(scope_marker),
            _normalized_key(domain),
            _normalized_key(topic),
        ]
    )
    return "concept:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _support_fingerprint(support_ids: tuple[str, ...], counterexample_ids: tuple[str, ...]) -> str:
    material = "support=" + ",".join(support_ids) + "|counter=" + ",".join(counterexample_ids)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _representative(values: list[str]) -> str:
    counts = Counter(value.strip() for value in values if value.strip())
    if not counts:
        raise ValueError("representative value requires at least one non-empty item")
    best_count = max(counts.values())
    return sorted(value for value, count in counts.items() if count == best_count)[0]


class ConceptDiscoveryEngine:
    """Group already-eligible evidence by same-scope domain/topic recurrence."""

    def __init__(self, policy: ConceptDiscoveryPolicy | None = None) -> None:
        self._policy = policy or ConceptDiscoveryPolicy()

    def discover(
        self, evidence: list[ConceptEvidence] | tuple[ConceptEvidence, ...]
    ) -> tuple[ConceptCandidate, ...]:
        rows = tuple(evidence)
        evidence_ids = [item.evidence_id for item in rows]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("concept discovery evidence IDs must be unique")

        grouped: dict[tuple[str, str, str], list[ConceptEvidence]] = defaultdict(list)
        for item in rows:
            topic_key = _normalized_key(item.topic)
            if topic_key in self._policy.generic_topics:
                continue
            grouped[(item.scope_marker, _normalized_key(item.domain), topic_key)].append(item)

        candidates: list[ConceptCandidate] = []
        for (scope_marker, _domain_key, _topic_key), group in grouped.items():
            support = tuple(sorted(item.evidence_id for item in group if not item.counterexample))
            counterexamples = tuple(
                sorted(item.evidence_id for item in group if item.counterexample)
            )
            if len(support) < self._policy.minimum_support_count:
                continue

            supporting_items = [item for item in group if not item.counterexample]
            domain = _representative([item.domain for item in supporting_items])
            topic = _representative([item.topic for item in supporting_items])
            project_values = {item.project for item in supporting_items if item.project}
            project = next(iter(project_values)) if len(project_values) == 1 else None
            sessions = {item.session_id for item in supporting_items if item.session_id}
            sources = {item.source for item in supporting_items if item.source}
            entities = {item.entity_name for item in supporting_items if item.entity_name}
            record_types = tuple(sorted({item.record_type for item in supporting_items}, key=str))
            if not self._meets_support_policy(
                support_count=len(support),
                distinct_session_count=len(sessions),
                record_types=record_types,
            ):
                continue
            if not self._has_abstraction_breadth(
                distinct_entity_count=len(entities),
                distinct_session_count=len(sessions),
                record_type_count=len(record_types),
            ):
                continue
            strong_verifications = sum(
                1
                for item in supporting_items
                if (item.verification or "").casefold() in self._policy.strong_verifications
            )
            confidence = self._formation_confidence(
                support_count=len(support),
                distinct_session_count=len(sessions),
                distinct_source_count=len(sources),
                distinct_entity_count=len(entities),
                record_type_count=len(record_types),
            )
            reasons = self._reasons(
                support_count=len(support),
                distinct_session_count=len(sessions),
                distinct_source_count=len(sources),
                distinct_entity_count=len(entities),
                record_type_count=len(record_types),
                strong_verification_count=strong_verifications,
                counterexample_count=len(counterexamples),
            )
            candidates.append(
                ConceptCandidate(
                    candidate_concept_id=_candidate_id(
                        scope_marker=scope_marker,
                        domain=domain,
                        topic=topic,
                    ),
                    scope_marker=scope_marker,
                    domain=domain,
                    topic=topic,
                    label=topic,
                    summary_candidate=None,
                    project=project,
                    supporting_evidence_ids=support,
                    counterexample_ids=counterexamples,
                    distinct_session_count=len(sessions),
                    distinct_source_count=len(sources),
                    distinct_entity_count=len(entities),
                    record_types=record_types,
                    strong_verification_count=strong_verifications,
                    formation_confidence=confidence,
                    reason_codes=reasons,
                    support_fingerprint=_support_fingerprint(support, counterexamples),
                )
            )
        return tuple(sorted(candidates, key=lambda item: item.candidate_concept_id))

    def prioritize_in_scope(
        self,
        candidates: list[ConceptCandidate] | tuple[ConceptCandidate, ...],
        *,
        salience_by_candidate_id: dict[str, SalienceInput],
        advisor: SalienceAdvisor | None = None,
    ) -> tuple[str, ...]:
        rows = tuple(candidates)
        if not rows:
            return ()
        scopes = {item.scope_marker for item in rows}
        if len(scopes) != 1:
            raise ValueError("concept Salience prioritization requires exactly one scope")
        ids = [item.candidate_concept_id for item in rows]
        if set(ids) != set(salience_by_candidate_id):
            raise ValueError("Salience inputs must match concept candidate IDs exactly")
        salience_candidates = [
            SalienceCandidate(
                candidate_id=item.candidate_concept_id,
                scope_marker=item.scope_marker,
                signals=salience_by_candidate_id[item.candidate_concept_id],
            )
            for item in rows
        ]
        return (advisor or SalienceAdvisor()).assess(salience_candidates).priority_order


    def _meets_support_policy(
        self,
        *,
        support_count: int,
        distinct_session_count: int,
        record_types: tuple[ConceptEvidenceType, ...],
    ) -> bool:
        knowledge_only = len(record_types) == 1 and str(record_types[0]) == "knowledge"
        if knowledge_only:
            return support_count >= self._policy.minimum_knowledge_only_support_count
        if support_count < self._policy.minimum_episode_or_mixed_support_count:
            return False
        has_episode = any(str(record_type) == "episode" for record_type in record_types)
        if has_episode and distinct_session_count < self._policy.minimum_distinct_sessions:
            return False
        return True

    def _has_abstraction_breadth(
        self,
        *,
        distinct_entity_count: int,
        distinct_session_count: int,
        record_type_count: int,
    ) -> bool:
        return (
            distinct_entity_count >= self._policy.minimum_distinct_entities
            or distinct_session_count >= 2
            or record_type_count >= 2
        )

    @staticmethod
    def _formation_confidence(
        *,
        support_count: int,
        distinct_session_count: int,
        distinct_source_count: int,
        distinct_entity_count: int,
        record_type_count: int,
    ) -> float:
        support_score = min(1.0, support_count / 5.0)
        session_score = min(1.0, distinct_session_count / 3.0)
        source_score = min(1.0, distinct_source_count / 3.0)
        entity_score = min(1.0, distinct_entity_count / 3.0)
        type_score = min(1.0, record_type_count / 2.0)
        value = (
            0.45 * support_score
            + 0.15 * session_score
            + 0.10 * source_score
            + 0.20 * entity_score
            + 0.10 * type_score
        )
        return round(max(0.0, min(1.0, value)), 6)

    def _reasons(
        self,
        *,
        support_count: int,
        distinct_session_count: int,
        distinct_source_count: int,
        distinct_entity_count: int,
        record_type_count: int,
        strong_verification_count: int,
        counterexample_count: int,
    ) -> tuple[ConceptReasonCode, ...]:
        reasons = [ConceptReasonCode.RECURRING_TOPIC]
        if support_count >= self._policy.broad_support_count:
            reasons.append(ConceptReasonCode.BROAD_SUPPORT)
        if distinct_session_count >= 2:
            reasons.append(ConceptReasonCode.MULTI_SESSION_SUPPORT)
        if distinct_source_count >= 2:
            reasons.append(ConceptReasonCode.MULTI_SOURCE_SUPPORT)
        if distinct_entity_count >= self._policy.minimum_distinct_entities:
            reasons.append(ConceptReasonCode.ENTITY_DIVERSITY)
        if record_type_count >= 2:
            reasons.append(ConceptReasonCode.MIXED_RECORD_TYPES)
        if strong_verification_count:
            reasons.append(ConceptReasonCode.STRONG_VERIFICATION_PRESENT)
        if counterexample_count:
            reasons.append(ConceptReasonCode.COUNTEREXAMPLES_PRESENT)
        return tuple(reasons)
