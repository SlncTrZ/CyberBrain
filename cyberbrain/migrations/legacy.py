# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from cyberbrain.core.content import content_hash, normalize_content
from cyberbrain.schemas.models import (
    DreamStatus,
    EpisodeRecord,
    EpisodeRole,
    KnowledgeRecord,
    KnowledgeStatus,
    Origin,
    Verification,
)


class MigrationDisposition(StrEnum):
    MIGRATE_ACTIVE = "migrate_active"
    MIGRATE_DEPRECATED = "migrate_deprecated"
    MIGRATE_EPISODE = "migrate_episode"
    REVIEW = "review"


@dataclass(frozen=True)
class LegacyMigrationPlan:
    point_id: str
    disposition: MigrationDisposition
    reasons: list[str] = field(default_factory=list)
    knowledge: KnowledgeRecord | None = None
    episode: EpisodeRecord | None = None


@dataclass(frozen=True)
class DuplicateActiveRepair:
    identity: tuple[str, str, str, str]
    winner_point_id: str | None
    superseded_point_ids: list[str]
    requires_review: bool
    reason: str


class LegacyMapper:
    """Pure deterministic legacy-to-V1 mapper. It never writes storage."""

    def plan_knowledge(self, point: dict[str, Any]) -> LegacyMigrationPlan:
        point_id = self._uuid(point.get("id"))
        payload = dict(point.get("payload") or {})
        if point_id is None:
            return self._review(point, "non_uuid_point_id")

        content = str(payload.get("content") or "").strip()
        if not content:
            return self._review(point, "missing_content")

        identity_keys = ("domain", "topic", "entity_type", "entity_name")
        identity_ready = all(str(payload.get(key) or "").strip() for key in identity_keys)
        if identity_ready:
            status_value = str(payload.get("status") or "").strip().casefold()
            if status_value not in {item.value for item in KnowledgeStatus}:
                return self._review(point, "unsupported_or_missing_status")
            record = KnowledgeRecord(
                id=point_id,
                content=normalize_content(content),
                summary=self._optional_string(payload.get("summary")),
                domain=str(payload["domain"]).strip(),
                topic=str(payload["topic"]).strip(),
                entity_type=str(payload["entity_type"]).strip(),
                entity_name=str(payload["entity_name"]).strip(),
                project=self._optional_string(payload.get("project")),
                version=self._positive_int(payload.get("version"), default=1),
                status=KnowledgeStatus(status_value),
                change_reason=self._optional_string(payload.get("change_reason")),
                importance=self._optional_string(payload.get("importance")),
                verification=self._verification(payload),
                provenance_type="legacy_qdrant",
                source=self._optional_string(payload.get("source")),
                origin=Origin.MIGRATION,
                content_hash=content_hash(content),
                context=self._legacy_context(payload),
                extensions=self._legacy_extensions(payload),
                created_at=self._timestamp(payload.get("timestamp")) or datetime.now(UTC),
                updated_at=self._timestamp(payload.get("timestamp")) or datetime.now(UTC),
            )
            disposition = (
                MigrationDisposition.MIGRATE_ACTIVE
                if record.status == KnowledgeStatus.ACTIVE
                else MigrationDisposition.MIGRATE_DEPRECATED
            )
            return LegacyMigrationPlan(
                point_id=str(point_id),
                disposition=disposition,
                reasons=["identity_ready"],
                knowledge=record,
            )

        if payload.get("session_id"):
            return self._review(point, "episodic_like_record_in_knowledge_collection")

        domain = str(payload.get("domain") or "").strip()
        if not domain:
            return self._review(point, "missing_domain_for_preservation")

        record = KnowledgeRecord(
            id=point_id,
            content=normalize_content(content),
            domain=domain,
            topic="legacy_source_chunk",
            entity_type="legacy_chunk",
            entity_name=f"legacy:{point_id}",
            project=self._optional_string(payload.get("project")),
            status=KnowledgeStatus.DEPRECATED,
            change_reason="preserved legacy source chunk; canonical identity unavailable",
            verification=Verification.UNVERIFIED,
            provenance_type="legacy_qdrant",
            source=self._optional_string(payload.get("source")),
            origin=Origin.MIGRATION,
            content_hash=content_hash(content),
            context={"legacy_collection": "cyberbrain_knowledge"},
            extensions=self._legacy_extensions(payload),
        )
        return LegacyMigrationPlan(
            point_id=str(point_id),
            disposition=MigrationDisposition.MIGRATE_DEPRECATED,
            reasons=["preserve_without_active_pollution", "canonical_identity_unavailable"],
            knowledge=record,
        )

    def plan_episode(self, point: dict[str, Any]) -> LegacyMigrationPlan:
        point_id = self._uuid(point.get("id"))
        payload = dict(point.get("payload") or {})
        if point_id is None:
            return self._review(point, "non_uuid_point_id")

        content = str(payload.get("content") or "").strip()
        session_id = str(payload.get("session_id") or "").strip()
        event_time = self._timestamp(payload.get("timestamp"))
        missing = []
        if not content:
            missing.append("content")
        if not session_id:
            missing.append("session_id")
        if event_time is None:
            missing.append("timestamp")
        if missing:
            return LegacyMigrationPlan(
                point_id=str(point_id),
                disposition=MigrationDisposition.REVIEW,
                reasons=[f"missing_episode_core:{','.join(missing)}"],
            )

        record = EpisodeRecord(
            id=point_id,
            content=normalize_content(content),
            summary=self._optional_string(payload.get("summary")),
            session_id=session_id,
            event_time=event_time,
            channel=self._optional_string(payload.get("channel")),
            role=self._role(payload),
            agent=self._optional_string(payload.get("agent_name")),
            project=self._optional_string(payload.get("project")),
            topic=self._optional_string(payload.get("topic")),
            importance=self._optional_string(payload.get("importance")),
            source=self._optional_string(payload.get("source")),
            dream_status=DreamStatus.SKIPPED,
            content_hash=content_hash(content),
            context=self._legacy_context(payload),
            extensions=self._legacy_extensions(payload),
            created_at=event_time,
        )
        return LegacyMigrationPlan(
            point_id=str(point_id),
            disposition=MigrationDisposition.MIGRATE_EPISODE,
            reasons=["episode_core_ready", "historical_migration_dream_skipped"],
            episode=record,
        )

    def duplicate_active_repairs(self, points: list[dict[str, Any]]) -> list[DuplicateActiveRepair]:
        groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        for point in points:
            payload = dict(point.get("payload") or {})
            if str(payload.get("status") or "").casefold() != "active":
                continue
            values = tuple(
                str(payload.get(key) or "").strip()
                for key in ("domain", "topic", "entity_type", "entity_name")
            )
            if not all(values):
                continue
            groups.setdefault(values, []).append(point)

        repairs: list[DuplicateActiveRepair] = []
        for identity, members in groups.items():
            if len(members) < 2:
                continue
            ranked = sorted(members, key=self._version_rank, reverse=True)
            top_rank = self._version_rank(ranked[0])
            tied = [member for member in ranked if self._version_rank(member) == top_rank]
            if len(tied) != 1:
                repairs.append(
                    DuplicateActiveRepair(
                        identity=identity,
                        winner_point_id=None,
                        superseded_point_ids=[],
                        requires_review=True,
                        reason="duplicate_active_top_rank_tie",
                    )
                )
                continue
            winner = str(ranked[0]["id"])
            repairs.append(
                DuplicateActiveRepair(
                    identity=identity,
                    winner_point_id=winner,
                    superseded_point_ids=[str(item["id"]) for item in ranked[1:]],
                    requires_review=False,
                    reason="highest_version_then_latest_timestamp",
                )
            )
        return repairs

    @staticmethod
    def _review(point: dict[str, Any], reason: str) -> LegacyMigrationPlan:
        return LegacyMigrationPlan(
            point_id=str(point.get("id") or ""),
            disposition=MigrationDisposition.REVIEW,
            reasons=[reason],
        )

    @staticmethod
    def _uuid(value: Any) -> UUID | None:
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _positive_int(value: Any, *, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed >= 1 else default

    @staticmethod
    def _timestamp(value: Any) -> datetime | None:
        if isinstance(value, (int, float)):
            numeric = float(value)
            if numeric > 10_000_000_000:
                numeric /= 1000.0
            try:
                return datetime.fromtimestamp(numeric, tz=UTC)
            except (OSError, OverflowError, ValueError):
                return None
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _role(payload: dict[str, Any]) -> EpisodeRole | None:
        raw = payload.get("role")
        if raw is None and isinstance(payload.get("extra_metadata"), dict):
            raw = payload["extra_metadata"].get("role")
        value = str(raw or "").strip().casefold()
        return EpisodeRole(value) if value in {item.value for item in EpisodeRole} else None

    @staticmethod
    def _verification(payload: dict[str, Any]) -> Verification:
        if str(payload.get("entity_type") or "").casefold() == "web_research":
            return Verification.RESEARCH
        return Verification.UNVERIFIED

    @staticmethod
    def _legacy_context(payload: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if payload.get("wing") is not None:
            result["legacy_wing"] = payload["wing"]
        return result

    @staticmethod
    def _legacy_extensions(payload: dict[str, Any]) -> dict[str, Any]:
        excluded = {
            "content",
            "summary",
            "domain",
            "topic",
            "entity_type",
            "entity_name",
            "project",
            "status",
            "version",
            "change_reason",
            "importance",
            "source",
            "timestamp",
            "session_id",
            "channel",
            "agent_name",
            "wing",
        }
        preserved = {key: value for key, value in payload.items() if key not in excluded}
        return {"legacy": preserved} if preserved else {}

    def _version_rank(self, point: dict[str, Any]) -> tuple[int, float]:
        payload = dict(point.get("payload") or {})
        version = self._positive_int(payload.get("version"), default=0)
        timestamp = self._timestamp(payload.get("timestamp"))
        timestamp_rank = timestamp.timestamp() if timestamp is not None else float("-inf")
        return version, timestamp_rank
