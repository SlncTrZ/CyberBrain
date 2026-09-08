# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.salience.benchmark import (
    BASELINES,
    Candidate,
    SalienceCase,
    consequence_only,
    evaluate_predictions,
    load_cases,
    recency_only,
    run,
    stable_input_order,
)

FIXTURE = Path("benchmarks/salience/cases.json")
REQUIRED_FAMILIES = {
    "prediction_error_vs_routine_success",
    "unresolved_blocker_vs_resolved_routine",
    "contradiction_vs_consistent_fact",
    "user_emphasis_vs_ordinary_detail",
    "high_vs_low_consequence",
    "novel_low_consequence_item",
    "recurrence_vs_one_off",
    "recent_routine_vs_older_high_consequence",
    "all_neutral_tie",
    "missing_signal_robustness",
    "scope_separated_not_comparable",
}


def test_fixture_is_reviewable_bounded_and_covers_required_families() -> None:
    cases = load_cases(FIXTURE)

    assert 20 <= len(cases) <= 40
    assert {case.family for case in cases} == REQUIRED_FAMILIES
    assert any(case.expected == "ambiguous" for case in cases)
    assert any(case.expected == "tie" for case in cases)
    assert any(case.expected == "not_comparable" for case in cases)

    for case in cases:
        for candidate in (case.candidate_a, case.candidate_b):
            assert candidate.scope_marker
            assert all(0.0 <= value <= 1.0 for value in candidate.signals.values())


def test_duplicate_case_ids_are_rejected(tmp_path: Path) -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["cases"].append(raw["cases"][0])
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate case_id"):
        load_cases(path)


def test_invalid_bounded_signal_is_rejected(tmp_path: Path) -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["cases"][0]["candidate_a"]["signals"]["consequence"] = 1.01
    path = tmp_path / "invalid-signal.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match=r"within \[0, 1\]"):
        load_cases(path)


def test_cross_scope_case_must_fail_closed_as_not_comparable(tmp_path: Path) -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    row = next(case for case in raw["cases"] if case["expected"] == "not_comparable")
    row["expected"] = "a_higher"
    path = tmp_path / "cross-scope.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="crosses scope boundaries"):
        load_cases(path)


def test_baselines_are_deterministic_and_scope_bounded() -> None:
    cases = load_cases(FIXTURE)
    first = run(FIXTURE)
    second = run(FIXTURE)

    assert first == second
    assert set(first["reports"]) == set(BASELINES)

    cross_scope = next(case for case in cases if case.expected == "not_comparable")
    assert stable_input_order(cross_scope) == "not_comparable"
    assert recency_only(cross_scope) == "not_comparable"
    assert consequence_only(cross_scope) == "not_comparable"


def test_missing_signal_defaults_are_deterministic_without_inventing_values() -> None:
    candidate_a = Candidate("a", "project:test", {"consequence": 0.7})
    candidate_b = Candidate("b", "project:test", {})
    case = SalienceCase(
        case_id="missing",
        family="missing_signal_robustness",
        candidate_a=candidate_a,
        candidate_b=candidate_b,
        expected="a_higher",
        rationale_category="missing_signal",
        rationale="test",
    )

    assert consequence_only(case) == "a_higher"
    assert recency_only(case) == "tie"


def test_pairwise_metrics_handle_ties_ambiguity_and_boundaries_correctly() -> None:
    same = "project:test"
    cases = [
        SalienceCase(
            "a",
            "metric",
            Candidate("a1", same, {}),
            Candidate("a2", same, {}),
            "a_higher",
            "metric",
            "a",
        ),
        SalienceCase(
            "b",
            "metric",
            Candidate("b1", same, {}),
            Candidate("b2", same, {}),
            "b_higher",
            "metric",
            "b",
        ),
        SalienceCase(
            "tie",
            "metric",
            Candidate("t1", same, {}),
            Candidate("t2", same, {}),
            "tie",
            "metric",
            "tie",
        ),
        SalienceCase(
            "ambiguous",
            "metric",
            Candidate("u1", same, {}),
            Candidate("u2", same, {}),
            "ambiguous",
            "metric",
            "ambiguous",
        ),
        SalienceCase(
            "boundary",
            "metric",
            Candidate("x1", "project:one", {}),
            Candidate("x2", "project:two", {}),
            "not_comparable",
            "metric",
            "boundary",
        ),
    ]
    predictions = {
        "a": "a_higher",
        "b": "a_higher",
        "tie": "tie",
        "ambiguous": "a_higher",
        "boundary": "not_comparable",
    }

    report = evaluate_predictions(cases, lambda case: predictions[case.case_id])

    assert report.total_cases == 5
    assert report.scored_cases == 3
    assert report.correct_cases == 2
    assert report.pairwise_accuracy == 0.666667
    assert report.tie_cases == 1
    assert report.tie_accuracy == 1.0
    assert report.ambiguous_cases == 1
    assert report.not_comparable_cases == 1
    assert report.boundary_safe_rate == 1.0


def test_reviewed_cyberbrain_policy_beats_all_trivial_baselines() -> None:
    from benchmarks.salience.cyberbrain_policy import evaluate_reviewed_policy

    cases = load_cases()
    reviewed = evaluate_reviewed_policy()
    baseline_reports = [evaluate_predictions(cases, predictor) for predictor in BASELINES.values()]

    assert reviewed.pairwise_accuracy == 1.0
    assert reviewed.tie_accuracy == 1.0
    assert reviewed.boundary_safe_rate == 1.0
    assert reviewed.pairwise_accuracy > max(report.pairwise_accuracy for report in baseline_reports)


def test_controlled_shadow_review_is_scope_safe_and_non_mutating() -> None:
    from benchmarks.salience.shadow_review import run_shadow_review

    report = run_shadow_review()

    assert report.total_cases == 28
    assert report.comparable_cases == 26
    assert report.boundary_cases == 2
    assert report.boundary_safe_rate == 1.0
    assert report.candidate_count == 52
    assert report.non_neutral_candidates > 0
