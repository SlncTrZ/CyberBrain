# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import pytest

from cyberbrain.salience import SalienceInput
from cyberbrain.working_memory import (
    TaskRelevance,
    WorkingMemoryCandidate,
    WorkingMemoryIdentity,
    WorkingMemoryItemKind,
    WorkingMemoryPolicy,
    WorkingMemorySelector,
)


def _identity(task: str = "task-a", scope: str = "project:alpha") -> WorkingMemoryIdentity:
    return WorkingMemoryIdentity(scope, "session-1", task)


def _candidate(
    candidate_id: str,
    *,
    identity: WorkingMemoryIdentity | None = None,
    kind: WorkingMemoryItemKind = WorkingMemoryItemKind.EVIDENCE,
    text: str | None = None,
    relevance: float = 0.8,
    consequence: float | None = None,
    reference_id: str | None = None,
    source_record_id: str | None = None,
) -> WorkingMemoryCandidate:
    return WorkingMemoryCandidate(
        candidate_id=candidate_id,
        identity=identity or _identity(),
        kind=kind,
        text=text or f"context for {candidate_id}",
        task_relevance=TaskRelevance(relevance, ("task_match",)),
        salience=SalienceInput(consequence=consequence),
        reference_id=reference_id,
        source_record_id=source_record_id,
    )


def test_task_relevance_precedes_salience() -> None:
    selector = WorkingMemorySelector(WorkingMemoryPolicy(minimum_task_relevance=0.0))
    rows = [
        _candidate("high-relevance", relevance=0.9, consequence=0.0),
        _candidate("high-salience", relevance=0.6, consequence=1.0),
    ]

    items, _report = selector.select(_identity(), rows)

    assert [item.candidate_id for item in items] == ["high-relevance", "high-salience"]
    assert items[0].task_relevance > items[1].task_relevance
    assert items[0].salience_score < items[1].salience_score


def test_irrelevant_candidates_are_filtered_before_salience_and_budget() -> None:
    selector = WorkingMemorySelector(WorkingMemoryPolicy(minimum_task_relevance=0.5))
    rows = [
        _candidate("keep", relevance=0.8),
        _candidate("drop", relevance=0.49, consequence=1.0),
    ]

    items, report = selector.select(_identity(), rows)

    assert [item.candidate_id for item in items] == ["keep"]
    assert report.relevant_count == 1
    assert "drop" in report.omitted_candidate_ids


def test_duplicate_suppression_keeps_higher_ranked_reference() -> None:
    selector = WorkingMemorySelector(WorkingMemoryPolicy(minimum_task_relevance=0.0))
    rows = [
        _candidate(
            "preferred",
            kind=WorkingMemoryItemKind.SELECTED_MEMORY_REFERENCE,
            relevance=0.9,
            reference_id="memory-1",
        ),
        _candidate(
            "duplicate",
            kind=WorkingMemoryItemKind.SELECTED_MEMORY_REFERENCE,
            relevance=0.6,
            consequence=1.0,
            reference_id="memory-1",
        ),
    ]

    items, report = selector.select(_identity(), rows)

    assert [item.candidate_id for item in items] == ["preferred"]
    assert report.duplicate_suppressed_count == 1
    assert "duplicate" in report.omitted_candidate_ids


def test_duplicate_text_is_normalized_when_no_reference_exists() -> None:
    selector = WorkingMemorySelector(WorkingMemoryPolicy(minimum_task_relevance=0.0))
    rows = [
        _candidate("a", text="Preserve   provenance", relevance=0.9),
        _candidate("b", text=" preserve provenance ", relevance=0.8),
    ]

    items, report = selector.select(_identity(), rows)

    assert [item.candidate_id for item in items] == ["a"]
    assert report.duplicate_suppressed_count == 1


def test_budget_and_item_caps_are_hard() -> None:
    selector = WorkingMemorySelector(
        WorkingMemoryPolicy(
            max_items=2,
            max_tokens=20,
            max_item_tokens=12,
            minimum_task_relevance=0.0,
        )
    )
    rows = [
        _candidate("a", text="a" * 80, relevance=1.0),
        _candidate("b", text="b" * 80, relevance=0.9),
        _candidate("c", text="c" * 80, relevance=0.8),
    ]

    items, report = selector.select(_identity(), rows)

    assert len(items) <= 2
    assert sum(item.estimated_tokens for item in items) <= 20
    assert all(item.estimated_tokens <= 12 for item in items)
    assert report.budget_omitted_count >= 1


def test_candidate_identity_mismatch_fails_closed() -> None:
    selector = WorkingMemorySelector()
    rows = [_candidate("wrong-task", identity=_identity(task="task-b"))]

    with pytest.raises(ValueError, match="exact working set identity"):
        selector.select(_identity(task="task-a"), rows)


def test_candidate_scope_mismatch_fails_closed() -> None:
    selector = WorkingMemorySelector()
    rows = [_candidate("wrong-scope", identity=_identity(scope="project:beta"))]

    with pytest.raises(ValueError, match="exact working set identity"):
        selector.select(_identity(scope="project:alpha"), rows)


def test_reference_kinds_require_reference_id() -> None:
    with pytest.raises(ValueError, match="requires reference_id"):
        _candidate("concept", kind=WorkingMemoryItemKind.CONCEPT_REFERENCE)


def test_candidate_count_ceiling_fails_closed() -> None:
    selector = WorkingMemorySelector(
        WorkingMemoryPolicy(max_items=2, max_candidates=2)
    )
    rows = [_candidate(str(index)) for index in range(3)]

    with pytest.raises(ValueError, match="exceeds max_candidates"):
        selector.select(_identity(), rows)
