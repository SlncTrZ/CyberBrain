# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime

from cyberbrain.migrations.audit import SchemaMigrationAudit
from cyberbrain.schemas.models import EpisodeRecord, KnowledgeRecord


class FakeRepository:
    def __init__(self, points: list[dict]) -> None:
        self.points = points
        self.requested_limit: int | None = None

    def scroll(self, collection: str, *, qdrant_filter=None, limit: int = 100):  # noqa: ANN001
        self.requested_limit = limit
        return self.points[:limit]


def _knowledge_payload() -> dict:
    return KnowledgeRecord(
        content="Canonical fact",
        domain="architecture",
        topic="CyberBrain",
        entity_type="decision",
        entity_name="reasoner_boundary",
        content_hash="0" * 64,
    ).model_dump(mode="json")


def test_schema_audit_classifies_current_legacy_future_and_invalid() -> None:
    current = _knowledge_payload()
    legacy = {"content": "legacy", "topic": "CyberBrain"}
    future = {**current, "schema_version": 2}
    invalid = {key: value for key, value in current.items() if key != "domain"}
    mismatch = {**current, "record_type": "episode"}
    repo = FakeRepository(
        [
            {"id": "current", "payload": current},
            {"id": "legacy", "payload": legacy},
            {"id": "future", "payload": future},
            {"id": "invalid", "payload": invalid},
            {"id": "mismatch", "payload": mismatch},
        ]
    )

    report = SchemaMigrationAudit(repo).inspect(
        collection="knowledge",
        record_kind="knowledge",
        max_points=100,
    )

    assert report.scanned == 5
    assert report.current == 1
    assert report.legacy == 1
    assert report.unsupported_future == 1
    assert report.invalid_current == 2
    assert report.versions == {1: 3, 0: 1, 2: 1}
    assert {issue.kind for issue in report.issues} == {
        "legacy_schema",
        "unsupported_future_schema",
        "invalid_current_schema",
        "record_type_mismatch",
    }


def test_schema_audit_detects_truncation_by_requesting_one_extra_point() -> None:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    points = []
    for index in range(4):
        payload = EpisodeRecord(
            content=f"episode {index}",
            session_id="s1",
            event_time=now,
            content_hash=f"{index}" * 64,
        ).model_dump(mode="json")
        points.append({"id": str(index), "payload": payload})
    repo = FakeRepository(points)

    report = SchemaMigrationAudit(repo).inspect(
        collection="episodic",
        record_kind="episode",
        max_points=3,
    )

    assert repo.requested_limit == 4
    assert report.scanned == 3
    assert report.truncated is True
    assert report.current == 3
