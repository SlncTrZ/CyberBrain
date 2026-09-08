# SPDX-License-Identifier: MPL-2.0

from benchmarks.evidence.outcome_readiness import census


def prediction(
    prediction_id: str,
    *,
    agent: str = "agent-a",
    session_id: str = "session-a",
    project: str = "project-a",
    topic: str = "topic-a",
    event_time: str = "2026-09-08T10:00:00+00:00",
    confidence: float = 0.8,
) -> dict:
    return {
        "id": prediction_id,
        "record_type": "episode",
        "session_id": session_id,
        "event_time": event_time,
        "agent": agent,
        "project": project,
        "topic": topic,
        "source": "cognitive_prediction",
        "context": {
            "cognition": {
                "kind": "prediction",
                "prediction_id": prediction_id,
                "expected_outcome": "validation passes",
                "confidence": confidence,
            }
        },
    }


def outcome(
    outcome_id: str,
    prediction_id: str,
    *,
    agent: str = "agent-a",
    session_id: str = "session-a",
    project: str = "project-a",
    topic: str = "topic-a",
    event_time: str = "2026-09-08T10:05:00+00:00",
    assessment: str = "confirmed",
    confidence: float = 0.8,
) -> dict:
    return {
        "id": outcome_id,
        "record_type": "episode",
        "session_id": session_id,
        "event_time": event_time,
        "agent": agent,
        "project": project,
        "topic": topic,
        "source": "cognitive_outcome",
        "context": {
            "cognition": {
                "kind": "outcome",
                "prediction_id": prediction_id,
                "expected_outcome": "validation passes",
                "prediction_confidence": confidence,
                "assessment": assessment,
            }
        },
    }


def test_census_counts_only_valid_prospective_pairs_and_agent_diversity() -> None:
    rows = [
        prediction("p1", session_id="s1", topic="tests"),
        outcome("o1", "p1", session_id="s1", topic="tests"),
        prediction("p2", session_id="s2", topic="deploy"),
        outcome("o2", "p2", session_id="s2", topic="deploy", assessment="contradicted"),
    ]

    report, pairs = census(rows)

    assert report.valid_pairs == 2
    assert report.invalid_prediction_records == 0
    assert report.invalid_outcome_records == 0
    assert report.historical_prediction_backfill_candidates == 0
    assert len(pairs) == 2
    summary = report.agent_summaries[0]
    assert summary.agent == "agent-a"
    assert summary.resolved_pairs == 2
    assert summary.distinct_sessions == 2
    assert summary.distinct_topics == 2
    assert summary.assessment_counts == {"confirmed": 1, "contradicted": 1}
    assert summary.evidence_ids == ("p1", "o1", "p2", "o2")
    assert summary.non_confirmed_outcome_ids == ("o2",)


def test_outcome_before_prediction_is_not_eligible() -> None:
    report, pairs = census(
        [
            prediction("p1", event_time="2026-09-08T10:00:00+00:00"),
            outcome("o1", "p1", event_time="2026-09-08T09:59:59+00:00"),
        ]
    )

    assert pairs == ()
    assert report.invalid_outcome_records == 1


def test_identity_substitution_breaks_pair_eligibility() -> None:
    report, pairs = census([prediction("p1"), outcome("o1", "p1", agent="agent-b")])

    assert pairs == ()
    assert report.invalid_outcome_records == 1


def test_historical_prediction_like_prose_is_never_backfilled() -> None:
    rows = [
        {
            "id": "ordinary-episode",
            "record_type": "episode",
            "session_id": "s1",
            "event_time": "2026-09-08T10:00:00+00:00",
            "agent": "agent-a",
            "source": "conversation",
            "content": "Prediction: this will work with confidence 0.9. Outcome: success.",
        }
    ]

    report, pairs = census(rows)

    assert pairs == ()
    assert report.predictions_seen == 0
    assert report.outcomes_seen == 0
    assert report.historical_prediction_backfill_candidates == 0


def test_latest_valid_outcome_wins_and_duplicates_are_counted() -> None:
    rows = [
        prediction("p1"),
        outcome("o1", "p1", event_time="2026-09-08T10:05:00+00:00", assessment="contradicted"),
        outcome("o2", "p1", event_time="2026-09-08T10:06:00+00:00", assessment="confirmed"),
    ]

    report, pairs = census(rows)

    assert report.valid_pairs == 1
    assert report.duplicate_outcomes == 1
    assert pairs[0].outcome_record_id == "o2"
    assert pairs[0].assessment == "confirmed"
