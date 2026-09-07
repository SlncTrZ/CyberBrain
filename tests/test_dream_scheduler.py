# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest

from cyberbrain.dreaming import scheduler


def test_parse_time_accepts_iso_seconds_and_milliseconds() -> None:
    expected = datetime(2026, 9, 7, 0, 0, tzinfo=UTC)

    assert scheduler.parse_time(expected) == expected
    assert scheduler.parse_time("2026-09-07T00:00:00Z") == expected
    assert scheduler.parse_time(expected.timestamp()) == expected
    assert scheduler.parse_time(expected.timestamp() * 1000) == expected
    assert scheduler.parse_time("not-a-time") is None


def test_collect_candidates_groups_sessions_and_counts_topics() -> None:
    points = [
        {
            "payload": {
                "session_id": "session-b",
                "event_time": "2026-09-06T23:00:00Z",
                "topic": "routing",
                "project": "CyberBrain",
            }
        },
        {
            "payload": {
                "session_id": "session-b",
                "event_time": "2026-09-06T23:30:00Z",
                "topic": "routing",
                "project": "CyberBrain",
            }
        },
        {
            "payload": {
                "session_id": "session-b",
                "event_time": "2026-09-06T23:20:00Z",
                "topic": "scheduler",
                "project": "CyberBrain",
            }
        },
        {
            "payload": {
                "session_id": "",
                "event_time": "2026-09-06T23:50:00Z",
            }
        },
    ]

    candidates = scheduler.collect_candidates(points)

    candidate = candidates["session-b"]
    assert candidate.episode_count == 3
    assert candidate.latest_event == datetime(2026, 9, 6, 23, 30, tzinfo=UTC)
    assert candidate.topics == Counter({"routing": 2, "scheduler": 1})
    assert candidate.projects == Counter({"CyberBrain": 3})


def test_top_values_is_frequency_then_casefold_deterministic() -> None:
    counter = Counter({"zeta": 2, "Alpha": 2, "beta": 1})

    assert scheduler.top_values(counter, 2) == ["Alpha", "zeta"]
    assert scheduler.top_values(counter, 0) == []

    with pytest.raises(ValueError, match="limit"):
        scheduler.top_values(counter, -1)


def test_parse_schedule_and_next_run_are_utc_safe() -> None:
    assert scheduler.parse_schedule("23:50") == (23, 50)

    before = datetime(2026, 9, 6, 22, 0, tzinfo=UTC)
    assert scheduler.next_run(before, 23, 50) == datetime(
        2026, 9, 6, 23, 50, tzinfo=UTC
    )

    after = datetime(2026, 9, 6, 23, 55, tzinfo=UTC)
    assert scheduler.next_run(after, 23, 50) == datetime(
        2026, 9, 7, 23, 50, tzinfo=UTC
    )

    with pytest.raises(ValueError):
        scheduler.parse_schedule("25:00")
    with pytest.raises(ValueError):
        scheduler.next_run(before, 24, 0)


def test_run_once_dry_run_never_enqueues(tmp_path, monkeypatch) -> None:
    old = datetime.now(UTC) - timedelta(hours=2)
    points = [
        {
            "payload": {
                "session_id": "session-dry",
                "event_time": old.isoformat(),
                "topic": "release",
                "project": "CyberBrain",
                "dream_status": "pending",
            }
        }
    ]
    monkeypatch.setattr(scheduler, "qdrant_scroll_pending", lambda: points)
    monkeypatch.setenv(
        "CYBERBRAIN_DREAM_QUEUE_DB",
        str(tmp_path / "dream_queue.sqlite"),
    )
    monkeypatch.setenv("CYBERBRAIN_DREAM_SCHEDULER_QUIET_MINUTES", "60")

    summary = scheduler.run_once(dry_run=True)

    assert summary["eligible_sessions"] == 1
    assert summary["enqueued_sessions"] == 0

    queue = scheduler.DreamQueue(tmp_path / "dream_queue.sqlite")
    with pytest.raises(KeyError):
        queue.get_by_session("session-dry")


def test_run_once_enqueues_once_and_then_skips_existing(tmp_path, monkeypatch) -> None:
    old = datetime.now(UTC) - timedelta(hours=2)
    points = [
        {
            "payload": {
                "session_id": "session-once",
                "event_time": old.isoformat(),
                "topic": "routing",
                "project": "CyberBrain",
                "dream_status": "pending",
            }
        }
    ]
    monkeypatch.setattr(scheduler, "qdrant_scroll_pending", lambda: points)
    queue_path = tmp_path / "dream_queue.sqlite"
    monkeypatch.setenv("CYBERBRAIN_DREAM_QUEUE_DB", str(queue_path))
    monkeypatch.setenv("CYBERBRAIN_DREAM_SCHEDULER_QUIET_MINUTES", "60")

    first = scheduler.run_once(dry_run=False)
    second = scheduler.run_once(dry_run=False)

    assert first["enqueued_sessions"] == 1
    assert second["enqueued_sessions"] == 0
    assert second["skipped_existing_jobs"] == 1

    job = scheduler.DreamQueue(queue_path).get_by_session("session-once")
    assert job.topics == ["routing"]
