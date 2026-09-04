# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from cyberbrain.core.content import content_hash, normalize_content
from cyberbrain.schemas.models import EpisodeRecord, KnowledgeRecord


def test_content_hash_normalizes_line_endings_and_outer_whitespace() -> None:
    assert content_hash("  hello\r\nworld  ") == content_hash("hello\nworld")


def test_normalize_content_rejects_empty() -> None:
    with pytest.raises(ValueError):
        normalize_content("   \n\r\n   ")


def test_knowledge_record_minimal_valid() -> None:
    content = "CyberBrain uses two Qdrant collections."
    record = KnowledgeRecord(
        content=content,
        domain="ops",
        topic="architecture",
        entity_type="decision",
        entity_name="qdrant_collection_model",
        content_hash=content_hash(content),
    )
    assert record.record_type == "knowledge"
    assert record.version == 1
    assert record.status.value == "active"


def test_knowledge_record_rejects_invalid_version() -> None:
    with pytest.raises(ValidationError):
        KnowledgeRecord(
            content="x",
            domain="ops",
            topic="test",
            entity_type="concept",
            entity_name="x",
            version=0,
            content_hash=content_hash("x"),
        )


def test_episode_requires_non_empty_session() -> None:
    with pytest.raises(ValidationError):
        EpisodeRecord(
            content="hello",
            session_id="   ",
            event_time=datetime.now(UTC),
            content_hash=content_hash("hello"),
        )


def test_episode_defaults_to_pending_dream() -> None:
    record = EpisodeRecord(
        content="hello",
        session_id="session-1",
        event_time=datetime.now(UTC),
        content_hash=content_hash("hello"),
    )
    assert record.dream_status.value == "pending"


def test_episode_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        EpisodeRecord(
            content="hello",
            session_id="session-1",
            event_time=datetime(2026, 9, 4, 12, 0),
            content_hash=content_hash("hello"),
        )


def test_episode_normalizes_offset_timestamp_to_utc() -> None:
    from datetime import timedelta, timezone

    record = EpisodeRecord(
        content="hello",
        session_id="session-1",
        event_time=datetime(2026, 9, 4, 19, 0, tzinfo=timezone(timedelta(hours=7))),
        content_hash=content_hash("hello"),
    )
    assert record.event_time == datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def test_knowledge_rejects_naive_explicit_timestamp() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        KnowledgeRecord(
            content="x",
            domain="ops",
            topic="test",
            entity_type="concept",
            entity_name="x",
            content_hash=content_hash("x"),
            created_at=datetime(2026, 9, 4, 12, 0),
        )
