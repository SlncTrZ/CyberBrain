# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

_REPLACEMENT_MARKERS = (
    "loại bỏ",
    "thay bằng",
    "replaced",
    "replaced by",
    "removed",
    "deprecated",
    "migrated from",
    "không dùng nữa",
)
_FAILURE_MARKERS = (
    "fail",
    "failed",
    "rejected",
    "abandoned",
    "không hoạt động",
    "bị lỗi",
)
_VERIFICATION_MARKERS = (
    "test thành công",
    "validated",
    "validation pass",
    "pass",
    "production ready",
)


@dataclass(frozen=True)
class NormalizedEvidence:
    id: str
    content: str
    domain: str | None = None
    topic: str | None = None
    entity_type: str | None = None
    entity_name: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    version: int | None = None
    status: str | None = None
    event_time: datetime | None = None
    supersedes_id: str | None = None
    superseded_by_id: str | None = None


@dataclass(frozen=True)
class EvolutionItem:
    id: str
    version: int | None
    event_time: str | None
    status: str | None
    relation_hint: str
    excerpt: str


@dataclass(frozen=True)
class EvolutionGroup:
    identity: dict[str, Any]
    chain: list[EvolutionItem]
    related_events: list[EvolutionItem]
    anomalies: list[str]


@dataclass(frozen=True)
class EvolutionBundle:
    topic: str | None
    groups: list[EvolutionGroup]
    ungrouped: list[EvolutionItem]


def normalize_record(point: dict[str, Any]) -> NormalizedEvidence:
    payload = point.get("payload") or point
    event_time = _parse_time(payload)
    version = payload.get("version")
    if not isinstance(version, int):
        try:
            version = int(version) if version is not None else None
        except (TypeError, ValueError):
            version = None

    return NormalizedEvidence(
        id=str(point.get("id") or payload.get("id") or ""),
        content=str(payload.get("content") or "").strip(),
        domain=_clean(payload.get("domain")),
        topic=_clean(payload.get("topic")),
        entity_type=_clean(payload.get("entity_type")),
        entity_name=_clean(payload.get("entity_name")),
        context=dict(payload.get("context") or {}),
        version=version,
        status=_clean(payload.get("status")),
        event_time=event_time,
        supersedes_id=_clean(payload.get("supersedes_id")),
        superseded_by_id=_clean(payload.get("superseded_by_id")),
    )


def build_evolution_bundle(records: list[NormalizedEvidence]) -> EvolutionBundle:
    groups: dict[tuple[Any, ...], list[NormalizedEvidence]] = {}
    ungrouped_records: list[NormalizedEvidence] = []

    for record in records:
        identity = _identity_key(record)
        if identity is None:
            ungrouped_records.append(record)
            continue
        groups.setdefault(identity, []).append(record)

    built_groups: list[EvolutionGroup] = []
    grouped_ids: set[str] = set()

    for identity, items in groups.items():
        sorted_items = sorted(items, key=_sort_key)
        chain = [_to_item(item, relation_hint="evolution_step") for item in sorted_items]
        grouped_ids.update(item.id for item in sorted_items)
        anomalies = _detect_anomalies(sorted_items)

        related_events = []
        for candidate in records:
            if candidate.id in grouped_ids:
                continue
            if candidate.topic != sorted_items[0].topic:
                continue
            if not candidate.content:
                continue
            hint = _relation_hint(candidate.content)
            if hint in {"replacement_or_removal", "failure", "verification"}:
                related_events.append(_to_item(candidate, relation_hint=hint))

        built_groups.append(
            EvolutionGroup(
                identity={
                    "domain": identity[0],
                    "topic": identity[1],
                    "entity_type": identity[2],
                    "entity_name": identity[3],
                    "context": dict(identity[4]),
                },
                chain=chain,
                related_events=sorted(related_events, key=lambda item: item.event_time or ""),
                anomalies=anomalies,
            )
        )

    ungrouped = [
        _to_item(record, relation_hint=_relation_hint(record.content))
        for record in ungrouped_records
    ]
    topic = next((record.topic for record in records if record.topic), None)
    return EvolutionBundle(topic=topic, groups=built_groups, ungrouped=ungrouped)


def _identity_key(record: NormalizedEvidence) -> tuple[Any, ...] | None:
    if not all([record.domain, record.topic, record.entity_type, record.entity_name]):
        return None
    return (
        record.domain,
        record.topic,
        record.entity_type,
        record.entity_name,
        tuple(sorted(record.context.items())),
    )


def _sort_key(record: NormalizedEvidence) -> tuple[int, int, str]:
    explicit_rank = 0 if record.supersedes_id or record.superseded_by_id else 1
    version = record.version if record.version is not None else 10**9
    event = record.event_time.isoformat() if record.event_time else "9999"
    return explicit_rank, version, event


def _detect_anomalies(items: list[NormalizedEvidence]) -> list[str]:
    anomalies: list[str] = []
    active = [item for item in items if item.status == "active"]
    if len(active) > 1:
        anomalies.append("multiple_active_versions")

    versions = sorted({item.version for item in items if item.version is not None})
    if len(versions) >= 2:
        expected = set(range(versions[0], versions[-1] + 1))
        missing = sorted(expected - set(versions))
        if missing:
            anomalies.append("version_gap:" + ",".join(str(value) for value in missing))

    if any(item.version is None for item in items):
        anomalies.append("missing_version")
    return anomalies


def _relation_hint(content: str) -> str:
    text = content.casefold()
    if any(marker in text for marker in _REPLACEMENT_MARKERS):
        return "replacement_or_removal"
    if any(marker in text for marker in _FAILURE_MARKERS):
        return "failure"
    if any(marker in text for marker in _VERIFICATION_MARKERS):
        return "verification"
    return "topic_related"


def _to_item(record: NormalizedEvidence, *, relation_hint: str) -> EvolutionItem:
    return EvolutionItem(
        id=record.id,
        version=record.version,
        event_time=record.event_time.astimezone(UTC).isoformat() if record.event_time else None,
        status=record.status,
        relation_hint=relation_hint,
        excerpt=_excerpt(record.content),
    )


def _excerpt(content: str, limit: int = 700) -> str:
    compact = re.sub(r"\s+", " ", content).strip()
    return compact[:limit]


def _parse_time(payload: dict[str, Any]) -> datetime | None:
    candidates = [payload.get("event_time"), payload.get("timestamp"), payload.get("date")]
    for value in candidates:
        if value is None:
            continue
        if isinstance(value, int | float):
            seconds = float(value) / 1000 if value > 10_000_000_000 else float(value)
            try:
                return datetime.fromtimestamp(seconds, tz=UTC)
            except (OverflowError, OSError, ValueError):
                continue
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
    return None


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
