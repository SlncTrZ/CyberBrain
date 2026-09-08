# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cyberbrain.working_memory import (
    TaskRelevance,
    WorkingMemoryCandidate,
    WorkingMemoryEmissionLedger,
    WorkingMemoryIdentity,
    WorkingMemoryItemKind,
    WorkingMemoryPolicy,
    WorkingMemoryService,
)

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def _identity(task: str = "task-a", session: str = "session-1") -> WorkingMemoryIdentity:
    return WorkingMemoryIdentity("project:alpha", session, task)


def _candidate(
    candidate_id: str,
    *,
    identity: WorkingMemoryIdentity | None = None,
    text: str | None = None,
) -> WorkingMemoryCandidate:
    return WorkingMemoryCandidate(
        candidate_id=candidate_id,
        identity=identity or _identity(),
        kind=WorkingMemoryItemKind.GOAL,
        text=text or f"goal {candidate_id}",
        task_relevance=TaskRelevance(1.0, ("active_goal",)),
    )


def test_activate_get_and_close_are_exact_identity_scoped() -> None:
    service = WorkingMemoryService()
    identity = _identity()

    snapshot = service.activate(identity, [_candidate("goal")], now=NOW)

    assert snapshot.revision == 1
    assert service.get(identity, now=NOW) == snapshot
    assert service.get(_identity(task="task-b"), now=NOW) is None
    assert service.get(_identity(session="session-2"), now=NOW) is None

    closeout = service.close(identity, now=NOW)
    assert closeout.existed is True
    assert closeout.final_revision == 1
    assert service.get(identity, now=NOW) is None


def test_reactivation_increments_revision_without_persistence() -> None:
    service = WorkingMemoryService()
    identity = _identity()

    first = service.activate(identity, [_candidate("goal", text="first")], now=NOW)
    second = service.activate(
        identity,
        [_candidate("goal", text="second")],
        now=NOW + timedelta(minutes=1),
    )

    assert first.revision == 1
    assert second.revision == 2
    assert second.created_at == first.created_at
    assert second.items[0].text == "second"


def test_ttl_expiry_removes_state() -> None:
    service = WorkingMemoryService(WorkingMemoryPolicy(ttl_seconds=60))
    identity = _identity()
    service.activate(identity, [_candidate("goal")], now=NOW)

    assert service.get(identity, now=NOW + timedelta(seconds=59)) is not None
    assert service.get(identity, now=NOW + timedelta(seconds=60)) is None


def test_purge_expired_removes_only_expired_working_sets() -> None:
    service = WorkingMemoryService(WorkingMemoryPolicy(ttl_seconds=60))
    old = _identity(task="old")
    fresh = _identity(task="fresh")
    service.activate(old, [_candidate("old", identity=old)], now=NOW)
    service.activate(
        fresh,
        [_candidate("fresh", identity=fresh)],
        now=NOW + timedelta(seconds=30),
    )

    removed = service.purge_expired(now=NOW + timedelta(seconds=61))

    assert removed == 1
    assert service.get(old, now=NOW + timedelta(seconds=61)) is None
    assert service.get(fresh, now=NOW + timedelta(seconds=61)) is not None


def test_emission_ledger_suppresses_unchanged_reinjection() -> None:
    service = WorkingMemoryService()
    identity = _identity()
    ledger = WorkingMemoryEmissionLedger(identity)
    service.activate(identity, [_candidate("goal")], now=NOW)

    first = service.emit(identity, ledger=ledger, now=NOW)
    second = service.emit(identity, ledger=ledger, now=NOW + timedelta(seconds=1))

    assert [item.candidate_id for item in first.items] == ["goal"]
    assert first.estimated_tokens > 0
    assert second.items == ()
    assert second.estimated_tokens == 0
    assert second.repeated_suppressed_count == 1


def test_changed_content_is_emitted_again_after_revision() -> None:
    service = WorkingMemoryService()
    identity = _identity()
    ledger = WorkingMemoryEmissionLedger(identity)
    service.activate(identity, [_candidate("goal", text="first")], now=NOW)
    service.emit(identity, ledger=ledger, now=NOW)
    service.activate(
        identity,
        [_candidate("goal", text="changed")],
        now=NOW + timedelta(seconds=10),
    )

    emission = service.emit(identity, ledger=ledger, now=NOW + timedelta(seconds=10))

    assert [item.text for item in emission.items] == ["changed"]
    assert emission.revision == 2


def test_emission_ledger_cannot_cross_task_boundary() -> None:
    service = WorkingMemoryService()
    task_a = _identity(task="a")
    task_b = _identity(task="b")
    service.activate(task_a, [_candidate("goal-a", identity=task_a)], now=NOW)

    with pytest.raises(ValueError, match="ledger identity mismatch"):
        service.emit(task_a, ledger=WorkingMemoryEmissionLedger(task_b), now=NOW)


def test_naive_timestamp_is_rejected() -> None:
    service = WorkingMemoryService()

    with pytest.raises(ValueError, match="timezone-aware"):
        service.activate(
            _identity(),
            [_candidate("goal")],
            now=datetime(2026, 9, 8, 12, 0),
        )
