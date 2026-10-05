# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime

from tests.test_cognitive_runtime_path import (
    FakeEvolution,
    FakeRepository,
    _knowledge_rows,
    _path,
    _prediction_pair,
    _trusted_identity,
)

NOW = datetime(2026, 9, 9, 4, 0, tzinfo=UTC)


def test_integrated_m3_to_m7_recall_scenario() -> None:
    repository = FakeRepository()
    rows = _knowledge_rows(count=10)
    for row in rows:
        repository.payloads[row["id"]] = {
            key: value for key, value in row.items() if key not in {"id", "score"}
        }

    path = _path(repository)
    result = path.process_recall(
        rows,
        query="adapter design architecture",
        kind="knowledge",
        requested_limit=5,
        project="CyberBrain",
        now=NOW,
    )

    # 1. Result bounded by requested_limit
    assert len(result) == 5
    # 2. M3 Salience & M5 Working Memory markers active on all returned rows
    assert all("_cognition" in row for row in result)
    assert all(row["_cognition"]["m5_working_memory_selected"] for row in result)
    assert all(row["_cognition"]["m3_salience_score"] > 0 for row in result)
    # 3. M4 Active concepts formation
    assert result[0]["_cognition"]["m4_active_concepts"]
    # 4. M7 Event-driven access updates recorded in repository
    assert any("access_count" in payload for _collection, _id, payload in repository.updates)


def test_m6_self_model_readiness_fails_closed_below_thresholds() -> None:
    repository = FakeRepository()
    # 5 prediction pairs (below the 20 minimum sample threshold)
    for index in range(5):
        repository.points.extend(_prediction_pair(index))
    evolution = FakeEvolution()
    path = _path(repository, evolution)

    result = path.run_self_model(trusted_identity=_trusted_identity(), generated_at=NOW)

    # Must fail closed: insufficient evidence, 0 hypotheses persisted
    assert result["status"] == "insufficient_evidence"
    assert result["persisted"] == 0
    assert result["trusted_resolved_outcomes"] == 5
    assert not evolution.calls


def test_m6_self_model_activates_when_thresholds_met() -> None:
    repository = FakeRepository()
    # 21 prediction pairs across sessions/topics (exceeds 20 samples, 3 sessions, 3 topics)
    for index in range(21):
        repository.points.extend(_prediction_pair(index))
    evolution = FakeEvolution()
    path = _path(repository, evolution)

    result = path.run_self_model(trusted_identity=_trusted_identity(), generated_at=NOW)

    # Must pass readiness gate: ready_read_only, hypotheses persisted
    assert result["status"] == "ready_read_only"
    assert result["trusted_resolved_outcomes"] >= 20
    assert result["persisted"] > 0
    assert evolution.calls
    # Hypotheses are isolated from ordinary recall
    assert all(call["ordinary_recall"] is False for call in evolution.calls)
