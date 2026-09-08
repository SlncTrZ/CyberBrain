# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import replace

import pytest

from cyberbrain.concepts import (
    ConceptDiscoveryEngine,
    ConceptDiscoveryPolicy,
    ConceptEvidence,
    ConceptEvidenceType,
    ConceptShadowRegistry,
)


def _evidence(evidence_id: str, topic: str, entity_name: str) -> ConceptEvidence:
    return ConceptEvidence(
        evidence_id,
        ConceptEvidenceType.KNOWLEDGE,
        "project:a",
        "code",
        topic,
        entity_name=entity_name,
    )


def _candidates():
    evidence = [
        _evidence("a1", "topic_a", "entity-a1"),
        _evidence("a2", "topic_a", "entity-a2"),
        _evidence("b1", "topic_b", "entity-b1"),
        _evidence("b2", "topic_b", "entity-b2"),
    ]
    engine = ConceptDiscoveryEngine(
        ConceptDiscoveryPolicy(minimum_knowledge_only_support_count=2)
    )
    return engine.discover(evidence)


def test_registry_reports_stability_across_identical_reruns() -> None:
    registry = ConceptShadowRegistry()
    candidates = _candidates()

    first = registry.observe(candidates)
    second = registry.observe(candidates)

    assert first.added_count == 2
    assert first.stable_count == 0
    assert second.added_count == 0
    assert second.removed_count == 0
    assert second.stable_count == 2
    assert second.changed_count == 0


def test_registry_detects_support_change_without_changing_identity() -> None:
    registry = ConceptShadowRegistry()
    candidates = _candidates()
    registry.observe(candidates)
    changed = list(candidates)
    changed[0] = replace(changed[0], support_fingerprint="different-fingerprint")

    report = registry.observe(changed)

    assert report.changed_count == 1
    assert report.stable_count == 1


def test_registry_rejects_duplicate_candidate_ids() -> None:
    registry = ConceptShadowRegistry()
    candidate = _candidates()[0]

    with pytest.raises(ValueError, match="candidate IDs must be unique"):
        registry.observe([candidate, candidate])
