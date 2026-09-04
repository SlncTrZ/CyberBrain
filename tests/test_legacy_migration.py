# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime

from cyberbrain.migrations.legacy import LegacyMapper, MigrationDisposition


def test_identity_ready_knowledge_maps_active() -> None:
    point = {
        "id": "11111111-1111-4111-8111-111111111111",
        "payload": {
            "content": "Use deterministic execution.",
            "domain": "architecture",
            "topic": "cyberbrain",
            "entity_type": "decision",
            "entity_name": "execution_boundary",
            "status": "active",
            "version": 3,
            "timestamp": "2026-09-04T03:00:00Z",
            "project": "CyberBrain",
        },
    }

    plan = LegacyMapper().plan_knowledge(point)

    assert plan.disposition == MigrationDisposition.MIGRATE_ACTIVE
    assert plan.knowledge is not None
    assert plan.knowledge.version == 3
    assert plan.knowledge.origin.value == "migration"
    assert plan.knowledge.created_at == datetime(2026, 9, 4, 3, 0, tzinfo=UTC)


def test_identity_missing_source_chunk_is_preserved_deprecated() -> None:
    point = {
        "id": "22222222-2222-4222-8222-222222222222",
        "payload": {
            "content": "legacy code chunk",
            "domain": "code",
            "project": "LegacyProject",
            "source": "/workspace/file.py",
        },
    }

    plan = LegacyMapper().plan_knowledge(point)

    assert plan.disposition == MigrationDisposition.MIGRATE_DEPRECATED
    assert plan.knowledge is not None
    assert plan.knowledge.status.value == "deprecated"
    assert plan.knowledge.topic == "legacy_source_chunk"
    assert plan.knowledge.entity_type == "legacy_chunk"


def test_episodic_like_record_inside_knowledge_requires_review() -> None:
    point = {
        "id": "33333333-3333-4333-8333-333333333333",
        "payload": {
            "content": "chat fragment",
            "domain": "ops",
            "session_id": "s1",
            "timestamp": 1_725_421_600,
        },
    }

    plan = LegacyMapper().plan_knowledge(point)

    assert plan.disposition == MigrationDisposition.REVIEW
    assert "episodic_like_record_in_knowledge_collection" in plan.reasons


def test_episode_numeric_timestamp_maps_and_skips_automatic_dreaming() -> None:
    point = {
        "id": "44444444-4444-4444-8444-444444444444",
        "payload": {
            "content": "historical chat",
            "session_id": "session-1",
            "timestamp": 1_725_421_600,
            "agent_name": "MeiLin",
            "project": "CyberBrain",
        },
    }

    plan = LegacyMapper().plan_episode(point)

    assert plan.disposition == MigrationDisposition.MIGRATE_EPISODE
    assert plan.episode is not None
    assert plan.episode.dream_status.value == "skipped"
    assert plan.episode.agent == "MeiLin"


def test_duplicate_active_repair_chooses_highest_version_then_timestamp() -> None:
    def point(point_id: str, version: int, timestamp: str) -> dict:
        return {
            "id": point_id,
            "payload": {
                "domain": "code",
                "topic": "adapter",
                "entity_type": "config",
                "entity_name": "Slnc_VideoAdapter",
                "status": "active",
                "version": version,
                "timestamp": timestamp,
            },
        }

    repairs = LegacyMapper().duplicate_active_repairs(
        [
            point("11111111-1111-4111-8111-111111111111", 1, "2026-01-01T00:00:00Z"),
            point("22222222-2222-4222-8222-222222222222", 3, "2026-03-01T00:00:00Z"),
            point("33333333-3333-4333-8333-333333333333", 2, "2026-02-01T00:00:00Z"),
        ]
    )

    assert len(repairs) == 1
    assert repairs[0].winner_point_id == "22222222-2222-4222-8222-222222222222"
    assert repairs[0].requires_review is False
    assert len(repairs[0].superseded_point_ids) == 2


def test_duplicate_active_rank_tie_requires_review() -> None:
    payload = {
        "domain": "code",
        "topic": "adapter",
        "entity_type": "config",
        "entity_name": "Slnc_VideoAdapter",
        "status": "active",
        "version": 2,
        "timestamp": "2026-02-01T00:00:00Z",
    }
    repairs = LegacyMapper().duplicate_active_repairs(
        [
            {"id": "11111111-1111-4111-8111-111111111111", "payload": dict(payload)},
            {"id": "22222222-2222-4222-8222-222222222222", "payload": dict(payload)},
        ]
    )

    assert repairs[0].requires_review is True
    assert repairs[0].winner_point_id is None
