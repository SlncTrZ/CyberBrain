# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import ValidationError

from cyberbrain.schemas.models import EpisodeRecord, KnowledgeRecord
from cyberbrain.storage.base import PointRepository

CURRENT_SCHEMA_VERSION = 1
RecordKind = Literal["knowledge", "episode"]


@dataclass(frozen=True)
class MigrationIssue:
    point_id: str
    kind: str
    detail: str


@dataclass(frozen=True)
class CollectionAuditReport:
    collection: str
    record_kind: RecordKind
    scanned: int
    truncated: bool
    current: int
    legacy: int
    unsupported_future: int
    invalid_current: int
    versions: dict[int, int] = field(default_factory=dict)
    issues: list[MigrationIssue] = field(default_factory=list)


class SchemaMigrationAudit:
    """Read-only canonical schema audit used before any migration is allowed."""

    def __init__(self, repository: PointRepository) -> None:
        self._repository = repository

    def inspect(
        self,
        *,
        collection: str,
        record_kind: RecordKind,
        max_points: int = 10_000,
    ) -> CollectionAuditReport:
        if max_points < 1:
            raise ValueError("max_points must be >= 1")
        points = self._repository.scroll(collection, limit=max_points + 1)
        truncated = len(points) > max_points
        points = points[:max_points]

        current = 0
        legacy = 0
        unsupported = 0
        invalid = 0
        versions: dict[int, int] = {}
        issues: list[MigrationIssue] = []

        model = KnowledgeRecord if record_kind == "knowledge" else EpisodeRecord
        expected_record_type = record_kind

        for point in points:
            payload = point.get("payload") or {}
            point_id = str(point.get("id") or payload.get("id") or "")
            raw_version = payload.get("schema_version", 0)
            try:
                version = int(raw_version)
            except (TypeError, ValueError):
                version = -1
            versions[version] = versions.get(version, 0) + 1

            if version < CURRENT_SCHEMA_VERSION:
                legacy += 1
                issues.append(
                    MigrationIssue(
                        point_id=point_id,
                        kind="legacy_schema",
                        detail=f"schema_version={raw_version!r}",
                    )
                )
                continue
            if version > CURRENT_SCHEMA_VERSION:
                unsupported += 1
                issues.append(
                    MigrationIssue(
                        point_id=point_id,
                        kind="unsupported_future_schema",
                        detail=f"schema_version={version}",
                    )
                )
                continue

            if payload.get("record_type") != expected_record_type:
                invalid += 1
                issues.append(
                    MigrationIssue(
                        point_id=point_id,
                        kind="record_type_mismatch",
                        detail=(
                            f"expected={expected_record_type!r} "
                            f"actual={payload.get('record_type')!r}"
                        ),
                    )
                )
                continue

            try:
                model.model_validate(payload)
            except ValidationError as exc:
                invalid += 1
                first = exc.errors()[0] if exc.errors() else {"msg": "invalid payload"}
                issues.append(
                    MigrationIssue(
                        point_id=point_id,
                        kind="invalid_current_schema",
                        detail=str(first.get("msg") or "invalid payload"),
                    )
                )
                continue
            current += 1

        return CollectionAuditReport(
            collection=collection,
            record_kind=record_kind,
            scanned=len(points),
            truncated=truncated,
            current=current,
            legacy=legacy,
            unsupported_future=unsupported,
            invalid_current=invalid,
            versions=versions,
            issues=issues,
        )
