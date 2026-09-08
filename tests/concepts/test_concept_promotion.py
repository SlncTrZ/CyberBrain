# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import replace

from cyberbrain.concepts import (
    ConceptDiscoveryEngine,
    ConceptDiscoveryPolicy,
    ConceptEvidence,
    ConceptEvidenceType,
    ConceptPromotionDecision,
    ConceptPromotionGate,
)


def _candidate(*, verified: bool = True, counterexample: bool = False):
    verification = "tested" if verified else "unverified"
    evidence = [
        ConceptEvidence(
            "k1",
            ConceptEvidenceType.KNOWLEDGE,
            "project:a",
            "code",
            "adapter_design",
            source="doc-a",
            entity_name="example-a",
            verification=verification,
        ),
        ConceptEvidence(
            "k2",
            ConceptEvidenceType.KNOWLEDGE,
            "project:a",
            "code",
            "adapter_design",
            source="doc-b",
            entity_name="example-b",
            verification=verification,
        ),
        ConceptEvidence(
            "k3",
            ConceptEvidenceType.KNOWLEDGE,
            "project:a",
            "code",
            "adapter_design",
            source="doc-c",
            entity_name="example-c",
            verification=verification,
        ),
    ]
    if counterexample:
        evidence.append(
            ConceptEvidence(
                "counter",
                ConceptEvidenceType.KNOWLEDGE,
                "project:a",
                "code",
                "adapter_design",
                entity_name="counterexample",
                counterexample=True,
            )
        )
    engine = ConceptDiscoveryEngine(
        ConceptDiscoveryPolicy(minimum_knowledge_only_support_count=3)
    )
    return engine.discover(evidence)[0]


def test_gate_requires_human_review_even_when_candidate_is_strong() -> None:
    evaluation = ConceptPromotionGate().evaluate(_candidate())

    assert evaluation.decision is ConceptPromotionDecision.REVIEW
    assert evaluation.reasons == ("human_review_required_before_knowledge_evolution",)


def test_gate_rejects_unverified_candidate() -> None:
    evaluation = ConceptPromotionGate().evaluate(_candidate(verified=False))

    assert evaluation.decision is ConceptPromotionDecision.REJECT
    assert "insufficient_strong_verification" in evaluation.reasons


def test_gate_rejects_unresolved_counterexample() -> None:
    evaluation = ConceptPromotionGate().evaluate(_candidate(counterexample=True))

    assert evaluation.decision is ConceptPromotionDecision.REJECT
    assert "counterexamples_require_resolution" in evaluation.reasons


def test_gate_rejects_low_confidence_even_if_other_counts_are_present() -> None:
    candidate = replace(_candidate(), formation_confidence=0.1)
    evaluation = ConceptPromotionGate().evaluate(candidate)

    assert evaluation.decision is ConceptPromotionDecision.REJECT
    assert "insufficient_formation_confidence" in evaluation.reasons
