# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from benchmarks.evidence.corpus_census import (
    ConceptEvidenceEligibility,
    census,
    classify_row,
)


def _knowledge(**overrides):
    row = {
        "id": "k1",
        "record_type": "knowledge",
        "content": "Stable reusable fact.",
        "summary": "Stable reusable fact.",
        "domain": "code",
        "topic": "adapter_design",
        "entity_type": "decision",
        "entity_name": "adapter-boundary",
        "status": "active",
        "verification": "tested",
        "origin": "ingestion",
        "provenance_type": "manual",
    }
    row.update(overrides)
    return row


def test_clean_active_knowledge_is_shadow_eligible() -> None:
    item = classify_row(_knowledge())
    assert item.eligibility is ConceptEvidenceEligibility.ELIGIBLE_SHADOW
    assert not item.legacy_chunk
    assert not item.research


def test_research_and_mixed_operational_are_review_only() -> None:
    research = classify_row(_knowledge(verification="research", source="web_search"))
    mixed = classify_row(_knowledge(content="Deploy completed; tests pass at commit abc123."))

    assert research.eligibility is ConceptEvidenceEligibility.REVIEW_ONLY
    assert mixed.eligibility is ConceptEvidenceEligibility.REVIEW_ONLY
    assert mixed.mixed_operational is True


def test_research_domain_is_review_only_even_without_research_verification() -> None:
    item = classify_row(
        _knowledge(domain="research", verification="unverified", source=None)
    )

    assert item.research is True
    assert item.eligibility is ConceptEvidenceEligibility.REVIEW_ONLY


def test_legacy_generic_and_inactive_are_excluded() -> None:
    legacy = classify_row(
        _knowledge(
            entity_type="legacy_chunk",
            topic="legacy_source_chunk",
            provenance_type="legacy_qdrant",
        )
    )
    inactive = classify_row(_knowledge(status="deprecated"))

    assert legacy.eligibility is ConceptEvidenceEligibility.EXCLUDED
    assert inactive.eligibility is ConceptEvidenceEligibility.EXCLUDED


def test_episode_requires_explicit_session_time_and_non_generic_topic() -> None:
    eligible = classify_row(
        {
            "id": "e1",
            "record_type": "episode",
            "content": "Observed recurring task behavior.",
            "session_id": "s1",
            "event_time": "2026-09-08T10:00:00Z",
            "topic": "adapter_design",
        }
    )
    generic = classify_row(
        {
            "id": "e2",
            "record_type": "episode",
            "content": "Transcript.",
            "session_id": "s2",
            "event_time": "2026-09-08T11:00:00Z",
            "topic": "chat_history",
        }
    )

    assert eligible.eligibility is ConceptEvidenceEligibility.ELIGIBLE_SHADOW
    assert generic.eligibility is ConceptEvidenceEligibility.EXCLUDED


def test_census_never_fabricates_historical_prediction_backfill() -> None:
    rows = [
        _knowledge(content="Prediction: this will work with confidence 0.9. Outcome: success."),
        {
            "id": "e1",
            "record_type": "episode",
            "content": "I predicted a result after seeing it.",
            "session_id": "s1",
            "event_time": "2026-09-08T10:00:00Z",
            "topic": "prediction_history",
        },
    ]

    report, _classified = census(rows)
    assert report.historical_prediction_backfill_candidates == 0
