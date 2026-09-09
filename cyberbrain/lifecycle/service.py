# SPDX-License-Identifier: MPL-2.0
"""M7 shadow evaluation, reversible soft suppression, and reactivation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from cyberbrain.schemas.models import (
    KnowledgeStatus,
    LifecycleState,
    RetentionDirective,
)
from cyberbrain.storage.base import PointRepository

from .evaluator import LifecycleEvaluator
from .models import LifecycleDecision, LifecycleDecisionKind, LifecycleSignals


@dataclass(frozen=True, slots=True)
class LifecycleShadowReport:
    scanned: int
    keep_active: int
    suppress: int
    remain_suppressed: int
    reactivate: int
    decisions: tuple[LifecycleDecision, ...]


class MemoryLifecycleService:
    """Lifecycle writes are metadata-only and never delete or rewrite record content."""

    def __init__(
        self,
        *,
        repository: PointRepository,
        evaluator: LifecycleEvaluator | None = None,
    ) -> None:
        self._repository = repository
        self._evaluator = evaluator or LifecycleEvaluator()

    def evaluate_payload(
        self,
        *,
        point_id: str,
        payload: dict[str, Any],
        now: datetime,
        salience_score: float = 0.0,
        concept_linked: bool = False,
        unresolved: bool = False,
        storage_pressure: float = 0.0,
        explicit_relevance: bool = False,
    ) -> LifecycleDecision:
        now = self._aware(now)
        created = self._payload_time(payload, "created_at") or self._payload_time(
            payload, "event_time"
        )
        if created is None:
            raise ValueError("lifecycle payload requires created_at or event_time")
        last_accessed = self._payload_time(payload, "last_accessed_at")
        age_days = max(0.0, (now - created).total_seconds() / 86400)
        days_since_last_access = (
            None
            if last_accessed is None
            else max(0.0, (now - last_accessed).total_seconds() / 86400)
        )
        state = LifecycleState(payload.get("lifecycle_state", LifecycleState.ACTIVE.value))
        directive = RetentionDirective(
            payload.get("retention_directive", RetentionDirective.DEFAULT.value)
        )
        status = str(payload.get("status") or "")
        cognition = (payload.get("context") or {}).get("cognition")
        contradicted = isinstance(cognition, dict) and cognition.get("assessment") == "contradicted"
        superseded_or_contradicted = (
            status
            in {
                KnowledgeStatus.SUPERSEDED.value,
                KnowledgeStatus.DEPRECATED.value,
                KnowledgeStatus.REJECTED.value,
            }
            or contradicted
        )
        return self._evaluator.evaluate(
            LifecycleSignals(
                record_id=point_id,
                lifecycle_state=state,
                retention_directive=directive,
                age_days=age_days,
                access_count=int(payload.get("access_count", 0) or 0),
                days_since_last_access=days_since_last_access,
                salience_score=salience_score,
                superseded_or_contradicted=superseded_or_contradicted,
                concept_linked=concept_linked,
                unresolved=unresolved,
                storage_pressure=storage_pressure,
                explicit_relevance=explicit_relevance,
            )
        )

    def shadow(
        self,
        points: list[dict[str, Any]],
        *,
        now: datetime,
        signal_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> LifecycleShadowReport:
        overrides = signal_overrides or {}
        decisions: list[LifecycleDecision] = []
        for point in points:
            point_id = str(point.get("id") or "")
            payload = dict(point.get("payload") or point)
            decisions.append(
                self.evaluate_payload(
                    point_id=point_id,
                    payload=payload,
                    now=now,
                    **dict(overrides.get(point_id) or {}),
                )
            )
        return LifecycleShadowReport(
            scanned=len(decisions),
            keep_active=sum(d.decision is LifecycleDecisionKind.KEEP_ACTIVE for d in decisions),
            suppress=sum(d.decision is LifecycleDecisionKind.SUPPRESS for d in decisions),
            remain_suppressed=sum(
                d.decision is LifecycleDecisionKind.REMAIN_SUPPRESSED for d in decisions
            ),
            reactivate=sum(d.decision is LifecycleDecisionKind.REACTIVATE for d in decisions),
            decisions=tuple(decisions),
        )

    def apply_decision(
        self,
        *,
        collection: str,
        point_id: UUID,
        decision: LifecycleDecision,
        now: datetime,
    ) -> None:
        now = self._aware(now)
        if str(point_id) != decision.record_id:
            raise ValueError("lifecycle decision point ID mismatch")
        if decision.decision is LifecycleDecisionKind.SUPPRESS:
            state = LifecycleState.SUPPRESSED
            ordinary_recall = False
        elif decision.decision is LifecycleDecisionKind.REACTIVATE:
            state = LifecycleState.ACTIVE
            ordinary_recall = True
        elif decision.decision is LifecycleDecisionKind.REMAIN_SUPPRESSED:
            state = LifecycleState.SUPPRESSED
            ordinary_recall = False
        else:
            state = LifecycleState.ACTIVE
            ordinary_recall = True
        self._repository.set_payload(
            collection,
            point_id=point_id,
            payload={
                "lifecycle_state": state.value,
                "ordinary_recall": ordinary_recall,
                "retention_score": decision.retention_score,
                "lifecycle_updated_at": now.isoformat(),
                "lifecycle_reason_codes": [reason.value for reason in decision.reason_codes],
                "updated_at": now.isoformat(),
            },
        )

    def record_access(
        self,
        *,
        collection: str,
        point_id: UUID,
        now: datetime,
    ) -> int:
        now = self._aware(now)
        point = self._repository.retrieve(collection, point_id)
        if point is None:
            raise KeyError(str(point_id))
        payload = dict(point.get("payload") or {})
        count = int(payload.get("access_count", 0) or 0) + 1
        self._repository.set_payload(
            collection,
            point_id=point_id,
            payload={
                "access_count": count,
                "last_accessed_at": now.isoformat(),
                "updated_at": now.isoformat(),
            },
        )
        return count

    @staticmethod
    def _payload_time(payload: dict[str, Any], key: str) -> datetime | None:
        value = payload.get(key)
        if value is None:
            return None
        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(UTC)

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("lifecycle timestamps must include a timezone")
        return value.astimezone(UTC)
