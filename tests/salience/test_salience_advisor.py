# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import pytest

from cyberbrain.core.metrics import MetricsRegistry
from cyberbrain.salience import (
    REVIEWED_SALIENCE_POLICY,
    SalienceAdvisor,
    SalienceCandidate,
    SalienceConfig,
    SalienceInput,
    SalienceScopeError,
    SalienceScorer,
    SalienceShadowObserver,
)


def _candidate(
    candidate_id: str, *, scope: str = "project:alpha", **signals: float
) -> SalienceCandidate:
    return SalienceCandidate(candidate_id, scope, SalienceInput(**signals))


def test_reviewed_policy_encodes_material_evidence_above_recency_and_novelty() -> None:
    assert REVIEWED_SALIENCE_POLICY.contradiction > REVIEWED_SALIENCE_POLICY.recency
    assert REVIEWED_SALIENCE_POLICY.consequence > REVIEWED_SALIENCE_POLICY.recency
    assert REVIEWED_SALIENCE_POLICY.consequence > REVIEWED_SALIENCE_POLICY.novelty
    assert REVIEWED_SALIENCE_POLICY.prediction_error > REVIEWED_SALIENCE_POLICY.recency


def test_advisor_orders_same_scope_candidates_without_mutating_input_order() -> None:
    candidates = [
        _candidate("routine", recency=1.0, consequence=0.1),
        _candidate("material", recency=0.2, consequence=0.9),
    ]
    original = [candidate.candidate_id for candidate in candidates]

    advisory = SalienceAdvisor().assess(candidates)

    assert [candidate.candidate_id for candidate in candidates] == original
    assert advisory.priority_order == ("material", "routine")
    assert tuple(item.candidate_id for item in advisory.assessments) == tuple(original)


def test_advisor_stably_preserves_input_order_for_equal_scores() -> None:
    candidates = [
        _candidate("first", recency=0.5),
        _candidate("second", recency=0.5),
    ]

    assert SalienceAdvisor().assess(candidates).priority_order == ("first", "second")


def test_advisor_fails_closed_before_cross_scope_comparison() -> None:
    candidates = [
        _candidate("alpha", scope="project:alpha", consequence=1.0),
        _candidate("beta", scope="project:beta", consequence=0.1),
    ]

    with pytest.raises(SalienceScopeError, match="share one authorized scope"):
        SalienceAdvisor().assess(candidates)


def test_candidate_requires_content_free_identity_and_scope_marker() -> None:
    with pytest.raises(ValueError, match="candidate_id"):
        SalienceCandidate(" ", "project:alpha", SalienceInput())
    with pytest.raises(ValueError, match="scope_marker"):
        SalienceCandidate("item", " ", SalienceInput())


def test_advisor_rejects_duplicate_candidate_ids() -> None:
    candidates = [
        _candidate("duplicate", consequence=1.0),
        _candidate("duplicate", consequence=0.5),
    ]

    with pytest.raises(ValueError, match="candidate IDs must be unique"):
        SalienceAdvisor().assess(candidates)


def test_shadow_reports_reordering_without_changing_candidates() -> None:
    metrics = MetricsRegistry()
    candidates = [
        _candidate("routine", recency=1.0, consequence=0.1),
        _candidate("material", recency=0.2, consequence=0.9),
    ]
    observer = SalienceShadowObserver(metrics=metrics)

    report = observer.observe(candidates)

    assert tuple(candidate.candidate_id for candidate in candidates) == ("routine", "material")
    assert report.reordered is True
    assert report.top1_changed is True
    assert report.priority_order == ("material", "routine")
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["salience_shadow_evaluated_total"] == 1
    assert snapshot["counters"]["salience_shadow_candidates_total"] == 2
    assert snapshot["counters"]["salience_shadow_top1_changed_total"] == 1


def test_shadow_empty_candidate_set_is_safe_and_bounded() -> None:
    report = SalienceShadowObserver().observe([])

    assert report.candidate_count == 0
    assert report.non_neutral_count == 0
    assert report.reordered is False
    assert report.top1_changed is False
    assert report.mean_score == 0.0
    assert report.priority_order == ()


def test_generic_equal_weight_scorer_remains_available_separately_from_policy() -> None:
    generic = SalienceScorer(SalienceConfig()).assess(
        SalienceInput(consequence=1.0, recency=0.0)
    )
    reviewed = SalienceAdvisor().assess(
        [_candidate("one", consequence=1.0, recency=0.0)]
    ).assessments[0].assessment

    assert generic.score == 0.5
    assert reviewed.score > generic.score
