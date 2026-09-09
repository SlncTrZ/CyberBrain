# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cyberbrain.lifecycle import (
    LifecycleDecisionKind,
    LifecycleEvaluator,
    LifecycleSignals,
    MemoryLifecycleService,
)
from cyberbrain.schemas.models import LifecycleState, RetentionDirective

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def test_stale_low_value_record_is_soft_suppressed_not_deleted() -> None:
    decision = LifecycleEvaluator().evaluate(
        LifecycleSignals(
            record_id=str(uuid4()),
            lifecycle_state=LifecycleState.ACTIVE,
            retention_directive=RetentionDirective.DEFAULT,
            age_days=365,
            access_count=0,
            days_since_last_access=None,
            salience_score=0.0,
            superseded_or_contradicted=True,
            storage_pressure=0.8,
        )
    )

    assert decision.decision is LifecycleDecisionKind.SUPPRESS
    assert decision.retention_score < 0.35


def test_explicit_keep_and_relevance_reactivate_suppressed_records() -> None:
    evaluator = LifecycleEvaluator()
    keep = evaluator.evaluate(
        LifecycleSignals(
            record_id="a",
            lifecycle_state=LifecycleState.SUPPRESSED,
            retention_directive=RetentionDirective.KEEP,
            age_days=500,
            access_count=0,
            days_since_last_access=None,
            salience_score=0.0,
        )
    )
    relevant = evaluator.evaluate(
        LifecycleSignals(
            record_id="b",
            lifecycle_state=LifecycleState.SUPPRESSED,
            retention_directive=RetentionDirective.DEFAULT,
            age_days=500,
            access_count=0,
            days_since_last_access=None,
            salience_score=0.0,
            explicit_relevance=True,
        )
    )

    assert keep.decision is LifecycleDecisionKind.REACTIVATE
    assert relevant.decision is LifecycleDecisionKind.REACTIVATE


class FakeRepository:
    def __init__(self) -> None:
        self.payloads = {}
        self.updates = []

    def retrieve(self, collection, point_id, **kwargs):  # noqa: ANN001, ANN201
        del collection, kwargs
        payload = self.payloads.get(str(point_id))
        return None if payload is None else {"id": str(point_id), "payload": dict(payload)}

    def set_payload(self, collection, *, point_id, payload):  # noqa: ANN001, ANN201
        self.updates.append((collection, str(point_id), dict(payload)))
        self.payloads.setdefault(str(point_id), {}).update(payload)


def test_service_shadow_apply_and_access_are_reversible_metadata_only() -> None:
    repository = FakeRepository()
    point_id = uuid4()
    repository.payloads[str(point_id)] = {
        "created_at": (NOW - timedelta(days=365)).isoformat(),
        "lifecycle_state": "active",
        "retention_directive": "default",
        "access_count": 0,
        "status": "deprecated",
    }
    service = MemoryLifecycleService(repository=repository)  # type: ignore[arg-type]
    decision = service.evaluate_payload(
        point_id=str(point_id),
        payload=repository.payloads[str(point_id)],
        now=NOW,
        storage_pressure=0.8,
    )
    assert decision.decision is LifecycleDecisionKind.SUPPRESS

    service.apply_decision(
        collection="knowledge",
        point_id=point_id,
        decision=decision,
        now=NOW,
    )
    assert repository.payloads[str(point_id)]["lifecycle_state"] == "suppressed"
    assert repository.payloads[str(point_id)]["ordinary_recall"] is False

    reactivation = service.evaluate_payload(
        point_id=str(point_id),
        payload=repository.payloads[str(point_id)],
        now=NOW,
        explicit_relevance=True,
    )
    assert reactivation.decision is LifecycleDecisionKind.REACTIVATE
    service.apply_decision(
        collection="knowledge",
        point_id=point_id,
        decision=reactivation,
        now=NOW,
    )
    assert repository.payloads[str(point_id)]["lifecycle_state"] == "active"
    assert repository.payloads[str(point_id)]["ordinary_recall"] is True

    assert service.record_access(collection="knowledge", point_id=point_id, now=NOW) == 1
    assert repository.payloads[str(point_id)]["access_count"] == 1
    assert "last_accessed_at" in repository.payloads[str(point_id)]
