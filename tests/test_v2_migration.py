# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime
from uuid import uuid4

from cyberbrain.migrations.v2 import V2MetadataNormalizer
from cyberbrain.schemas.models import (
    EpisodeRecord,
    IdentityTrust,
    KnowledgeRecord,
    KnowledgeRecordClass,
    LifecycleState,
)

NOW = datetime(2026, 9, 8, 15, 0, tzinfo=UTC)


def knowledge_v1() -> dict:
    point_id = uuid4()
    return {
        "id": str(point_id),
        "schema_version": 1,
        "record_type": "knowledge",
        "content": "canonical knowledge",
        "summary": None,
        "domain": "ops",
        "topic": "deploy",
        "entity_type": "concept",
        "entity_name": "deploy-check",
        "project": " CyberBrain ",
        "tags": ["a", "a", "b"],
        "keywords": [],
        "version": 1,
        "status": "active",
        "supersedes_id": None,
        "superseded_by_id": None,
        "change_reason": None,
        "importance": None,
        "verification": "unverified",
        "confidence": None,
        "provenance_type": "legacy_qdrant",
        "source": None,
        "evidence_ids": [],
        "origin": "migration",
        "dream_run_id": None,
        "negative_knowledge": False,
        "content_hash": "0" * 64,
        "embedding_version": None,
        "context": {},
        "extensions": {},
        "created_at": "2026-09-01T00:00:00+00:00",
        "updated_at": "2026-09-01T00:00:00+00:00",
    }


def episode_v1(*, agent: str | None = "chatgpt") -> dict:
    point_id = uuid4()
    return {
        "id": str(point_id),
        "schema_version": 1,
        "record_type": "episode",
        "content": "episode",
        "summary": None,
        "session_id": "s1",
        "event_time": "2026-09-01T00:00:00+00:00",
        "channel": "mcp",
        "role": "assistant",
        "agent": agent,
        "project": "CyberBrain",
        "topic": "deploy",
        "keywords": [],
        "importance": None,
        "source": "conversation",
        "dream_status": "processed",
        "dream_run_id": None,
        "dreamed_at": None,
        "content_hash": "1" * 64,
        "embedding_version": None,
        "context": {},
        "extensions": {},
        "created_at": "2026-09-01T00:00:00+00:00",
    }


def test_v1_knowledge_gets_complete_v2_metadata_without_fabricating_identity() -> None:
    record = V2MetadataNormalizer().normalize_knowledge(
        knowledge_v1(), source_collection="knowledge_v1", migrated_at=NOW
    )

    assert isinstance(record, KnowledgeRecord)
    assert record.schema_version == 2
    assert record.record_class is KnowledgeRecordClass.KNOWLEDGE
    assert record.project == "CyberBrain"
    assert record.tenant is None
    assert record.user is None
    assert record.agent is None
    assert record.identity_trust is IdentityTrust.UNSPECIFIED
    assert record.lifecycle_state is LifecycleState.ACTIVE
    assert record.ordinary_recall is True
    assert record.tags == ["a", "b"]
    assert record.extensions["migration_v2"]["source_schema_version"] == 1


def test_pre_p3_agent_metadata_migrates_as_legacy_untrusted() -> None:
    record = V2MetadataNormalizer().normalize_episode(
        episode_v1(), source_collection="episodic_v1", migrated_at=NOW
    )

    assert isinstance(record, EpisodeRecord)
    assert record.schema_version == 2
    assert record.agent == "chatgpt"
    assert record.identity_trust is IdentityTrust.LEGACY_UNTRUSTED
    assert record.updated_at == record.created_at


def test_existing_authenticated_v2_identity_is_preserved() -> None:
    payload = EpisodeRecord(
        content="trusted",
        session_id="s2",
        event_time=NOW,
        agent="agent-a",
        identity_trust=IdentityTrust.AUTHENTICATED,
        content_hash="2" * 64,
    ).model_dump(mode="json")

    record = V2MetadataNormalizer().normalize_episode(
        payload, source_collection="episodic_v2", migrated_at=NOW
    )

    assert record.identity_trust is IdentityTrust.AUTHENTICATED


def test_malformed_raw_episode_is_preserved_in_quarantine_not_dropped() -> None:
    point_id = uuid4()
    raw = {
        "id": str(point_id),
        "payload": {
            "content": "orphan legacy episode",
            "session_id": "",
            "timestamp": "2026-09-06T12:42:27+00:00",
            "agent_name": "pi",
            "project": "",
        },
    }

    record = V2MetadataNormalizer().raw_legacy_episode(
        raw,
        source_collection="cyberbrain_episodic",
        migrated_at=NOW,
    )

    assert isinstance(record, KnowledgeRecord)
    assert record.id == point_id
    assert record.record_class is KnowledgeRecordClass.MIGRATION_QUARANTINE
    assert record.lifecycle_state is LifecycleState.SUPPRESSED
    assert record.ordinary_recall is False
    assert record.identity_trust is IdentityTrust.LEGACY_UNTRUSTED
    assert record.content == "orphan legacy episode"


def test_stage_fingerprint_changes_when_only_vector_changes() -> None:
    from scripts.stage_v2_migration import _fingerprint

    point_id = str(uuid4())
    first = {
        "knowledge": [
            {"id": point_id, "payload": {"content": "same"}, "vector": [0.1, 0.2]}
        ]
    }
    second = {
        "knowledge": [
            {"id": point_id, "payload": {"content": "same"}, "vector": [0.1, 0.3]}
        ]
    }

    assert _fingerprint(first) != _fingerprint(second)


def test_stage_completion_requires_source_stability_and_exact_target_counts() -> None:
    from scripts.stage_v2_migration import _migration_complete

    report = {
        "source_stable": True,
        "target_knowledge": 10,
        "target_episodic": 5,
        "target_knowledge_count": 10,
        "target_episodic_count": 5,
    }
    assert _migration_complete(report) is True

    extra_target = dict(report, target_knowledge_count=11)
    assert _migration_complete(extra_target) is False

    missing_target = dict(report, target_episodic_count=4)
    assert _migration_complete(missing_target) is False

    unstable_source = dict(report, source_stable=False)
    assert _migration_complete(unstable_source) is False
