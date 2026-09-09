# SPDX-License-Identifier: MPL-2.0
"""Deterministic schema-V2 metadata normalization and legacy preservation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from cyberbrain.core.content import content_hash, normalize_content
from cyberbrain.migrations.legacy import LegacyMapper, MigrationDisposition
from cyberbrain.schemas.models import (
    CURRENT_SCHEMA_VERSION,
    EpisodeRecord,
    IdentityTrust,
    KnowledgeRecord,
    KnowledgeRecordClass,
    KnowledgeStatus,
    LifecycleState,
    Origin,
    RetentionDirective,
    Verification,
)


class V2MetadataNormalizer:
    """Normalize canonical V1 payloads into the complete V2 metadata contract."""

    def normalize_knowledge(
        self,
        payload: dict[str, Any],
        *,
        source_collection: str,
        migrated_at: datetime,
    ) -> KnowledgeRecord:
        migrated_at = self._aware(migrated_at)
        data = dict(payload)
        source_schema = self._schema_version(data)
        data.update(
            {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "record_class": data.get("record_class", KnowledgeRecordClass.KNOWLEDGE.value),
                "tenant": self._optional_string(data.get("tenant")),
                "user": self._optional_string(data.get("user")),
                "agent": self._optional_string(data.get("agent")),
                "project": self._optional_string(data.get("project")),
                "session_id": self._optional_string(data.get("session_id")),
                "identity_trust": self._identity_trust(
                    data.get("identity_trust"),
                    agent=data.get("agent"),
                    source_schema=source_schema,
                ).value,
                "lifecycle_state": data.get("lifecycle_state", LifecycleState.ACTIVE.value),
                "retention_score": self._bounded_float(data.get("retention_score"), default=1.0),
                "retention_directive": data.get(
                    "retention_directive", RetentionDirective.DEFAULT.value
                ),
                "access_count": self._non_negative_int(data.get("access_count")),
                "last_accessed_at": data.get("last_accessed_at"),
                "lifecycle_updated_at": data.get("lifecycle_updated_at") or migrated_at.isoformat(),
                "lifecycle_reason_codes": self._reason_codes(
                    data.get("lifecycle_reason_codes"),
                    fallback="schema_v2_migration_default",
                ),
            }
        )
        record_class = KnowledgeRecordClass(data["record_class"])
        status = KnowledgeStatus(data.get("status", KnowledgeStatus.ACTIVE.value))
        data["ordinary_recall"] = bool(
            data.get(
                "ordinary_recall",
                record_class is KnowledgeRecordClass.KNOWLEDGE and status is KnowledgeStatus.ACTIVE,
            )
        )
        data["tags"] = self._dedupe_strings(data.get("tags"))
        data["keywords"] = self._dedupe_strings(data.get("keywords"))
        data["updated_at"] = data.get("updated_at") or data.get("created_at") or migrated_at
        data["extensions"] = self._migration_extensions(
            data.get("extensions"),
            source_collection=source_collection,
            source_schema=source_schema,
            migrated_at=migrated_at,
        )
        return KnowledgeRecord.model_validate(data)

    def normalize_episode(
        self,
        payload: dict[str, Any],
        *,
        source_collection: str,
        migrated_at: datetime,
    ) -> EpisodeRecord:
        migrated_at = self._aware(migrated_at)
        data = dict(payload)
        source_schema = self._schema_version(data)
        data.update(
            {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "tenant": self._optional_string(data.get("tenant")),
                "user": self._optional_string(data.get("user")),
                "agent": self._optional_string(data.get("agent")),
                "project": self._optional_string(data.get("project")),
                "topic": self._optional_string(data.get("topic")),
                "identity_trust": self._identity_trust(
                    data.get("identity_trust"),
                    agent=data.get("agent"),
                    source_schema=source_schema,
                ).value,
                "lifecycle_state": data.get("lifecycle_state", LifecycleState.ACTIVE.value),
                "ordinary_recall": bool(data.get("ordinary_recall", True)),
                "retention_score": self._bounded_float(data.get("retention_score"), default=1.0),
                "retention_directive": data.get(
                    "retention_directive", RetentionDirective.DEFAULT.value
                ),
                "access_count": self._non_negative_int(data.get("access_count")),
                "last_accessed_at": data.get("last_accessed_at"),
                "lifecycle_updated_at": data.get("lifecycle_updated_at") or migrated_at.isoformat(),
                "lifecycle_reason_codes": self._reason_codes(
                    data.get("lifecycle_reason_codes"),
                    fallback="schema_v2_migration_default",
                ),
                "updated_at": data.get("updated_at")
                or data.get("created_at")
                or data.get("event_time")
                or migrated_at,
            }
        )
        data["keywords"] = self._dedupe_strings(data.get("keywords"))
        data["extensions"] = self._migration_extensions(
            data.get("extensions"),
            source_collection=source_collection,
            source_schema=source_schema,
            migrated_at=migrated_at,
        )
        return EpisodeRecord.model_validate(data)

    def raw_legacy_knowledge(
        self,
        point: dict[str, Any],
        *,
        source_collection: str,
        migrated_at: datetime,
    ) -> KnowledgeRecord:
        plan = LegacyMapper().plan_knowledge(point)
        if plan.knowledge is None:
            return self.quarantine_raw(
                point,
                source_collection=source_collection,
                reason="legacy_knowledge_unmappable:" + ",".join(plan.reasons),
                migrated_at=migrated_at,
            )
        return self.normalize_knowledge(
            plan.knowledge.model_dump(mode="json"),
            source_collection=source_collection,
            migrated_at=migrated_at,
        )

    def raw_legacy_episode(
        self,
        point: dict[str, Any],
        *,
        source_collection: str,
        migrated_at: datetime,
    ) -> EpisodeRecord | KnowledgeRecord:
        plan = LegacyMapper().plan_episode(point)
        if plan.disposition is MigrationDisposition.MIGRATE_EPISODE and plan.episode is not None:
            return self.normalize_episode(
                plan.episode.model_dump(mode="json"),
                source_collection=source_collection,
                migrated_at=migrated_at,
            )
        return self.quarantine_raw(
            point,
            source_collection=source_collection,
            reason="legacy_episode_unmappable:" + ",".join(plan.reasons),
            migrated_at=migrated_at,
        )

    def quarantine_raw(
        self,
        point: dict[str, Any],
        *,
        source_collection: str,
        reason: str,
        migrated_at: datetime,
    ) -> KnowledgeRecord:
        migrated_at = self._aware(migrated_at)
        point_id = UUID(str(point["id"]))
        payload = dict(point.get("payload") or {})
        content = normalize_content(payload.get("content") or f"Legacy record {point_id}")
        raw_metadata = {key: value for key, value in payload.items() if key != "content"}
        return KnowledgeRecord(
            id=point_id,
            record_class=KnowledgeRecordClass.MIGRATION_QUARANTINE,
            content=content,
            summary=self._optional_string(payload.get("summary")),
            domain="migration",
            topic="quarantine",
            entity_type="legacy_record",
            entity_name=f"legacy:{source_collection}:{point_id}",
            project=self._optional_string(payload.get("project")),
            status=KnowledgeStatus.DEPRECATED,
            change_reason=reason,
            verification=Verification.UNVERIFIED,
            provenance_type="legacy_qdrant_quarantine",
            source=self._optional_string(payload.get("source")),
            origin=Origin.MIGRATION,
            content_hash=content_hash(content),
            identity_trust=(
                IdentityTrust.LEGACY_UNTRUSTED
                if payload.get("agent") or payload.get("agent_name")
                else IdentityTrust.UNSPECIFIED
            ),
            lifecycle_state=LifecycleState.SUPPRESSED,
            ordinary_recall=False,
            retention_score=0.0,
            lifecycle_updated_at=migrated_at,
            lifecycle_reason_codes=("migration_quarantine",),
            context={"quarantine_reason": reason},
            extensions={
                "migration_v2": {
                    "source_collection": source_collection,
                    "source_schema_version": self._schema_version(payload),
                    "migrated_at": migrated_at.isoformat(),
                    "vector_preserved": True,
                    "quarantine": True,
                },
                "legacy_raw_metadata": raw_metadata,
            },
            created_at=self._timestamp(payload.get("timestamp")) or migrated_at,
            updated_at=migrated_at,
        )

    @staticmethod
    def _identity_trust(
        value: object,
        *,
        agent: object,
        source_schema: int,
    ) -> IdentityTrust:
        try:
            if value is not None:
                return IdentityTrust(str(value))
        except ValueError:
            pass
        if source_schema < CURRENT_SCHEMA_VERSION and str(agent or "").strip():
            return IdentityTrust.LEGACY_UNTRUSTED
        return IdentityTrust.UNSPECIFIED

    @staticmethod
    def _migration_extensions(
        value: object,
        *,
        source_collection: str,
        source_schema: int,
        migrated_at: datetime,
    ) -> dict[str, Any]:
        extensions = dict(value) if isinstance(value, dict) else {}
        extensions["migration_v2"] = {
            "source_collection": source_collection,
            "source_schema_version": source_schema,
            "migrated_at": migrated_at.isoformat(),
            "vector_preserved": True,
        }
        return extensions

    @staticmethod
    def _schema_version(payload: dict[str, Any]) -> int:
        try:
            return int(payload.get("schema_version", 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _optional_string(value: object) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _dedupe_strings(value: object) -> list[str]:
        if not isinstance(value, list | tuple):
            return []
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))

    @staticmethod
    def _reason_codes(value: object, *, fallback: str) -> list[str]:
        if not isinstance(value, list | tuple):
            return [fallback]
        cleaned = list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))
        return cleaned or [fallback]

    @staticmethod
    def _bounded_float(value: object, *, default: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return parsed if 0 <= parsed <= 1 else default

    @staticmethod
    def _non_negative_int(value: object) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 0
        return max(0, parsed)

    @staticmethod
    def _timestamp(value: object) -> datetime | None:
        if isinstance(value, int | float):
            number = float(value)
            if number > 10_000_000_000:
                number /= 1000
            try:
                return datetime.fromtimestamp(number, tz=UTC)
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
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("migration timestamp must include timezone")
        return value.astimezone(UTC)
