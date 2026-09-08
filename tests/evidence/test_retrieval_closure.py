# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.retrieval.review_closure import (
    RetrievalReviewCase,
    RetrievalReviewDataset,
    closure_checklist,
    load_review_dataset,
    run,
    summarize,
)
from benchmarks.salience.benchmark import run as run_salience

FIXTURE = Path("benchmarks/retrieval/review_cases.json")


def _case(
    case_id: str,
    *,
    disposition: str = "tie",
    relevant: tuple[str, ...] = ("target",),
    vector: tuple[str, ...] = ("target", "v2"),
    lexical: tuple[str, ...] = ("target", "l2"),
    known_vector_miss: bool = False,
    scope_leakage: bool = False,
    shadow_failure: bool = False,
) -> RetrievalReviewCase:
    return RetrievalReviewCase(
        case_id=case_id,
        query_fingerprint=f"sanitized:{case_id}",
        scope_marker="project:test",
        vector_top_ids=vector,
        lexical_top_ids=lexical,
        reviewed_relevant_ids=relevant,
        known_vector_miss=known_vector_miss,
        scope_leakage=scope_leakage,
        shadow_failure=shadow_failure,
        disposition=disposition,
        token_delta=-1.0,
        latency_delta_ms=3.0,
        scoring_observation="test observation",
    )


def test_bundled_fixture_summary_and_safe_closure_state() -> None:
    report = run(FIXTURE)
    summary = report["summary"]

    assert summary["sample_count"] == 8
    assert summary["reviewed_sample_count"] == 8
    assert summary["lexical_wins"] == 2
    assert summary["vector_wins"] == 0
    assert summary["ties"] == 6
    assert summary["known_miss_rescue_count"] == 1
    assert summary["scope_leakage_count"] == 0
    assert summary["failure_count"] == 0
    assert summary["top1_change_improved_count"] == 2
    assert summary["top1_change_regressed_count"] == 0
    assert summary["mean_token_delta"] == -12.75
    assert summary["mean_latency_delta_ms"] == 3.25
    assert report["closure"]["decision_state"] == "insufficient_evidence"
    assert report["closure"]["changes_runtime_behavior"] is False


def test_duplicate_review_case_ids_are_rejected(tmp_path: Path) -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["cases"].append(raw["cases"][0])
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate case_id"):
        load_review_dataset(path)


def test_raw_query_content_is_rejected_in_review_fixture(tmp_path: Path) -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["cases"][0]["query"] = "raw production content should not be stored here"
    path = tmp_path / "raw-query.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="raw query content is not allowed"):
        load_review_dataset(path)


def test_reviewed_disposition_requires_relevance_labels(tmp_path: Path) -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["cases"][0]["reviewed_relevant_ids"] = []
    path = tmp_path / "unlabeled-reviewed.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="needs reviewed_relevant_ids"):
        load_review_dataset(path)


def test_leakage_failure_and_known_miss_rescue_counters() -> None:
    dataset = RetrievalReviewDataset(
        evidence_source="owner_reviewed_observation",
        cases=(
            _case(
                "rescued",
                disposition="lexical_better",
                vector=("v1", "v2"),
                lexical=("target", "l2"),
                known_vector_miss=True,
                scope_leakage=True,
            ),
            _case("failed", disposition="vector_better", shadow_failure=True),
        ),
    )

    summary = summarize(dataset)

    assert summary.scope_leakage_count == 1
    assert summary.failure_count == 1
    assert summary.known_vector_miss_count == 1
    assert summary.known_miss_rescue_count == 1
    assert summary.lexical_wins == 1
    assert summary.vector_wins == 1


def test_empty_and_unknown_evidence_fail_safely_without_promotion() -> None:
    empty = RetrievalReviewDataset(evidence_source="owner_reviewed_observation", cases=())
    empty_summary = summarize(empty)
    empty_gate = closure_checklist(empty, empty_summary)

    assert empty_gate["decision_state"] == "insufficient_evidence"
    assert empty_gate["changes_runtime_behavior"] is False

    unknown = RetrievalReviewDataset(
        evidence_source="owner_reviewed_observation",
        cases=(
            _case("unknown", disposition="unknown", relevant=()),
        ),
    )
    unknown_summary = summarize(unknown)
    unknown_gate = closure_checklist(unknown, unknown_summary, min_reviewed=1)

    assert unknown_summary.unknown == 1
    assert unknown_gate["decision_state"] == "insufficient_evidence"
    assert unknown_gate["changes_runtime_behavior"] is False


def test_unsafe_reviewed_evidence_retains_vector_only() -> None:
    dataset = RetrievalReviewDataset(
        evidence_source="owner_reviewed_observation",
        cases=(
            _case("benefit", disposition="lexical_better", vector=("v1",), lexical=("target",)),
            _case("tie-1"),
            _case("tie-2"),
            _case("tie-3"),
            _case("leak", scope_leakage=True),
        ),
    )
    summary = summarize(dataset)
    gate = closure_checklist(dataset, summary)

    assert gate["checks"]["bounded_benefit_observed"] is True
    assert gate["checks"]["scope_leakage_zero"] is False
    assert gate["decision_state"] == "retain_vector_only"
    assert gate["changes_runtime_behavior"] is False


def test_clean_owner_reviewed_evidence_is_only_a_promotion_review_candidate() -> None:
    dataset = RetrievalReviewDataset(
        evidence_source="owner_reviewed_observation",
        cases=(
            _case("benefit", disposition="lexical_better", vector=("v1",), lexical=("target",)),
            _case("tie-1"),
            _case("tie-2"),
            _case("tie-3"),
            _case("tie-4"),
        ),
    )
    summary = summarize(dataset)
    gate = closure_checklist(dataset, summary)

    assert gate["decision_state"] == "candidate_for_owner_promotion_review"
    assert gate["changes_runtime_behavior"] is False


def test_evidence_harnesses_do_not_mutate_runtime_or_config_files() -> None:
    protected = Path("pyproject.toml")
    before = protected.read_bytes()

    run(FIXTURE)
    run_salience(Path("benchmarks/salience/cases.json"))

    assert protected.read_bytes() == before
