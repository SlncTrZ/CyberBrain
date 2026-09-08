# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import pytest

from cyberbrain.concepts import (
    ConceptDiscoveryEngine,
    ConceptDiscoveryPolicy,
    ConceptEvidence,
    ConceptEvidenceType,
    ConceptReasonCode,
)
from cyberbrain.salience import SalienceInput


def _evidence(
    evidence_id: str,
    *,
    topic: str = "adapter_design",
    scope: str = "project:alpha",
    domain: str = "code",
    record_type: ConceptEvidenceType = ConceptEvidenceType.KNOWLEDGE,
    session_id: str | None = None,
    source: str | None = None,
    verification: str | None = None,
    project: str | None = "alpha",
    entity_name: str | None = None,
    counterexample: bool = False,
) -> ConceptEvidence:
    return ConceptEvidence(
        evidence_id=evidence_id,
        record_type=record_type,
        scope_marker=scope,
        domain=domain,
        topic=topic,
        project=project,
        entity_name=entity_name or evidence_id,
        session_id=session_id,
        source=source,
        verification=verification,
        counterexample=counterexample,
    )


def _permissive_engine() -> ConceptDiscoveryEngine:
    return ConceptDiscoveryEngine(
        ConceptDiscoveryPolicy(minimum_knowledge_only_support_count=2)
    )


def test_discovers_stable_same_scope_topic_candidate() -> None:
    engine = ConceptDiscoveryEngine()
    rows = [
        _evidence("k1", source="doc-a"),
        _evidence("k2", source="doc-b"),
        _evidence(
            "e1",
            record_type=ConceptEvidenceType.EPISODE,
            session_id="s1",
            source="session",
        ),
        _evidence(
            "e2",
            record_type=ConceptEvidenceType.EPISODE,
            session_id="s2",
            source="session",
        ),
    ]

    first = engine.discover(rows)
    second = engine.discover(list(reversed(rows)))

    assert first == second
    assert len(first) == 1
    candidate = first[0]
    assert candidate.topic == "adapter_design"
    assert candidate.label == "adapter_design"
    assert candidate.summary_candidate is None
    assert candidate.supporting_evidence_ids == ("e1", "e2", "k1", "k2")
    assert candidate.distinct_session_count == 2
    assert candidate.distinct_source_count == 3
    assert candidate.distinct_entity_count == 4
    assert set(candidate.record_types) == {
        ConceptEvidenceType.KNOWLEDGE,
        ConceptEvidenceType.EPISODE,
    }
    assert ConceptReasonCode.RECURRING_TOPIC in candidate.reason_codes
    assert ConceptReasonCode.MULTI_SESSION_SUPPORT in candidate.reason_codes
    assert ConceptReasonCode.MULTI_SOURCE_SUPPORT in candidate.reason_codes
    assert ConceptReasonCode.ENTITY_DIVERSITY in candidate.reason_codes
    assert ConceptReasonCode.MIXED_RECORD_TYPES in candidate.reason_codes


def test_repeated_versions_of_same_entity_do_not_form_abstraction() -> None:
    engine = _permissive_engine()
    rows = [
        _evidence("v1", entity_name="same-entity"),
        _evidence("v2", entity_name="same-entity"),
        _evidence("v3", entity_name="same-entity"),
    ]

    assert engine.discover(rows) == ()


def test_default_policy_requires_broad_recurrence_for_knowledge_only_cluster() -> None:
    engine = ConceptDiscoveryEngine()
    rows = [
        _evidence(f"k{index}", entity_name=f"entity-{index}")
        for index in range(4)
    ]

    assert engine.discover(rows) == ()
    rows.append(_evidence("k5", entity_name="entity-5"))
    assert len(engine.discover(rows)) == 1


def test_singleton_and_generic_topics_do_not_form_candidates() -> None:
    engine = ConceptDiscoveryEngine()
    rows = [
        _evidence("single", topic="one_off"),
        _evidence("chat-a", topic="chat_history"),
        _evidence("chat-b", topic="chat_history"),
    ]

    assert engine.discover(rows) == ()


def test_scope_boundaries_produce_distinct_candidate_identity() -> None:
    engine = _permissive_engine()
    rows = [
        _evidence("a1", scope="project:alpha"),
        _evidence("a2", scope="project:alpha"),
        _evidence("b1", scope="project:beta", project="beta"),
        _evidence("b2", scope="project:beta", project="beta"),
    ]

    candidates = engine.discover(rows)

    assert len(candidates) == 2
    assert {item.scope_marker for item in candidates} == {"project:alpha", "project:beta"}
    assert len({item.candidate_concept_id for item in candidates}) == 2
    assert all(len(item.supporting_evidence_ids) == 2 for item in candidates)


def test_counterexamples_are_retained_but_not_counted_as_support() -> None:
    engine = _permissive_engine()
    rows = [
        _evidence("support-1"),
        _evidence("support-2"),
        _evidence("counter", counterexample=True),
    ]

    candidate = engine.discover(rows)[0]

    assert candidate.supporting_evidence_ids == ("support-1", "support-2")
    assert candidate.counterexample_ids == ("counter",)
    assert ConceptReasonCode.COUNTEREXAMPLES_PRESENT in candidate.reason_codes


def test_duplicate_evidence_ids_fail_closed() -> None:
    engine = ConceptDiscoveryEngine()
    rows = [_evidence("duplicate"), _evidence("duplicate")]

    with pytest.raises(ValueError, match="evidence IDs must be unique"):
        engine.discover(rows)


def test_strong_verification_is_counted_without_becoming_truth() -> None:
    engine = _permissive_engine()
    rows = [
        _evidence("tested", verification="tested"),
        _evidence("unverified", verification="unverified"),
    ]

    candidate = engine.discover(rows)[0]

    assert candidate.strong_verification_count == 1
    assert ConceptReasonCode.STRONG_VERIFICATION_PRESENT in candidate.reason_codes
    assert 0 <= candidate.formation_confidence <= 1


def test_salience_prioritizes_candidates_without_changing_concept_identity() -> None:
    engine = _permissive_engine()
    candidates = engine.discover(
        [
            _evidence("a1", topic="alpha_topic"),
            _evidence("a2", topic="alpha_topic"),
            _evidence("b1", topic="beta_topic"),
            _evidence("b2", topic="beta_topic"),
        ]
    )
    by_topic = {item.topic: item for item in candidates}
    before = {
        item.candidate_concept_id: item.support_fingerprint for item in candidates
    }
    inputs = {
        by_topic["alpha_topic"].candidate_concept_id: SalienceInput(recency=1.0),
        by_topic["beta_topic"].candidate_concept_id: SalienceInput(consequence=1.0),
    }

    order = engine.prioritize_in_scope(candidates, salience_by_candidate_id=inputs)

    assert order[0] == by_topic["beta_topic"].candidate_concept_id
    assert {
        item.candidate_concept_id: item.support_fingerprint for item in candidates
    } == before


def test_salience_priority_refuses_cross_scope_comparison() -> None:
    engine = _permissive_engine()
    candidates = engine.discover(
        [
            _evidence("a1", scope="project:alpha"),
            _evidence("a2", scope="project:alpha"),
            _evidence("b1", scope="project:beta", project="beta"),
            _evidence("b2", scope="project:beta", project="beta"),
        ]
    )
    inputs = {
        item.candidate_concept_id: SalienceInput(consequence=1.0)
        for item in candidates
    }

    with pytest.raises(ValueError, match="exactly one scope"):
        engine.prioritize_in_scope(candidates, salience_by_candidate_id=inputs)
