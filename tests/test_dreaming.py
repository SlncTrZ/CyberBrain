# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime, timedelta

from cyberbrain.dreaming.planner import DreamingPlanner, EpisodeSnippet, TopicExtractor


def test_topic_extractor_prefers_repeated_terms() -> None:
    extractor = TopicExtractor()
    topics = extractor.extract(
        [
            "MeiLin becomes a CyberBrain client.",
            "CyberBrain owns memory and Dreaming.",
            "CyberBrain keeps MeiLin compatibility.",
        ],
        limit=2,
    )
    assert topics[0] == "CyberBrain"
    assert "MeiLin" in topics


def test_dream_plan_builds_old_to_new_temporal_buckets() -> None:
    now = datetime(2026, 9, 4, 0, 0, tzinfo=UTC)
    episodes = [
        EpisodeSnippet("CyberBrain design", now - timedelta(hours=2)),
        EpisodeSnippet("CyberBrain Dreaming design", now),
    ]
    plan = DreamingPlanner().plan(episodes, topic_limit=2)

    assert plan.session_start == now - timedelta(hours=2)
    assert plan.session_end == now
    assert [bucket.name for bucket in plan.buckets] == [
        "older_than_1y",
        "6_to_12_months",
        "3_to_6_months",
        "1_to_3_months",
        "1_to_4_weeks",
        "last_week",
    ]
    assert plan.buckets[0].start is None
    assert plan.buckets[-1].end == now
