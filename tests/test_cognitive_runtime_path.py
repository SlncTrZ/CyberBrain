# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cyberbrain.cognition.runtime_path import CognitiveRuntimePath
from cyberbrain.core.metrics import MetricsRegistry
from cyberbrain.lifecycle import MemoryLifecycleService
from cyberbrain.schemas.models import EpisodeRecord, IdentityTrust
from cyberbrain.self_model import SelfModelPersistence, SelfModelService
from cyberbrain.tenancy import IdentityScope, TrustedIdentityEvidence

NOW = datetime(2026, 9, 9, 4, 0, tzinfo=UTC)


class FakeRepository:
    def __init__(self) -> None:
        self.payloads: dict[str, dict] = {}
        self.points: list[dict] = []
        self.updates: list[tuple[str, str, dict]] = []

    def retrieve(self, collection, point_id, **kwargs):  # noqa: ANN001, ANN201
        del collection, kwargs
        payload = self.payloads.get(str(point_id))
        return None if payload is None else {"id": str(point_id), "payload": dict(payload)}

    def set_payload(self, collection, *, point_id, payload):  # noqa: ANN001, ANN201
        row = self.payloads.setdefault(str(point_id), {})
        row.update(payload)
        self.updates.append((collection, str(point_id), dict(payload)))

    def scroll(self, collection, *, qdrant_filter=None, limit=100):  # noqa: ANN001, ANN201
        del collection
        rows = list(self.points)
        if qdrant_filter:
            for condition in qdrant_filter.get("must", []):
                key = condition.get("key")
                value = (condition.get("match") or {}).get("value")
                rows = [row for row in rows if (row.get("payload") or {}).get(key) == value]
        return rows[:limit]


class FakeEvolution:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def store(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(dict(kwargs))
        return kwargs


def _path(
    repository: FakeRepository, evolution: FakeEvolution | None = None
) -> CognitiveRuntimePath:
    evolution = evolution or FakeEvolution()
    self_model = SelfModelService()
    persistence = SelfModelPersistence(
        evolution=evolution,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        collection="knowledge",
    )
    lifecycle = MemoryLifecycleService(repository=repository)  # type: ignore[arg-type]
    return CognitiveRuntimePath(
        repository=repository,  # type: ignore[arg-type]
        knowledge_collection="knowledge",
        episodic_collection="episodes",
        metrics=MetricsRegistry(),
        self_model=self_model,
        self_model_persistence=persistence,
        memory_lifecycle=lifecycle,
    )


def _knowledge_rows(count: int = 15) -> list[dict]:
    rows = []
    for index in range(count):
        point_id = uuid4()
        payload = {
            "id": str(point_id),
            "score": 0.8 - (index * 0.005),
            "content": f"Adapter design evidence {index}",
            "summary": f"Adapter design {index}",
            "domain": "engineering",
            "topic": "adapter_design",
            "entity_type": "note",
            "entity_name": f"entity-{index}",
            "verification": "tested" if index < 5 else "unverified",
            "importance": "high" if index == 10 else "medium",
            "created_at": (NOW - timedelta(days=365)).isoformat(),
            "updated_at": (NOW - timedelta(days=365)).isoformat(),
            "status": "active",
            "record_class": "knowledge",
            "ordinary_recall": True,
            "lifecycle_state": "active",
            "retention_directive": "default",
            "access_count": 0,
        }
        rows.append(payload)
    return rows


def test_recall_path_activates_m3_m4_m5_and_event_driven_m7() -> None:
    repository = FakeRepository()
    rows = _knowledge_rows()
    for row in rows:
        repository.payloads[row["id"]] = {
            key: value for key, value in row.items() if key not in {"id", "score"}
        }

    path = _path(repository)
    result = path.process_recall(
        rows,
        query="adapter design architecture",
        kind="knowledge",
        requested_limit=5,
        project="CyberBrain",
        now=NOW,
    )

    assert len(result) == 5
    assert all("_cognition" in row for row in result)
    assert all(row["_cognition"]["m5_working_memory_selected"] for row in result)
    assert all(row["_cognition"]["m3_salience_score"] > 0 for row in result)
    assert result[0]["_cognition"]["m4_active_concepts"]
    assert any("access_count" in payload for _collection, _id, payload in repository.updates)
    assert any(payload.get("ordinary_recall") is False for _c, _id, payload in repository.updates)


def test_exact_recall_reactivates_suppressed_normal_record_but_not_self_model_class() -> None:
    repository = FakeRepository()
    point_id = uuid4()
    repository.payloads[str(point_id)] = {
        "content": "old but explicitly fetched",
        "created_at": (NOW - timedelta(days=400)).isoformat(),
        "lifecycle_state": "suppressed",
        "ordinary_recall": False,
        "retention_directive": "default",
        "record_class": "knowledge",
        "access_count": 0,
    }
    path = _path(repository)
    row = {"id": str(point_id), **repository.payloads[str(point_id)]}

    result = path.process_exact_recall(row, kind="knowledge", now=NOW)

    assert result["ordinary_recall"] is True
    assert result["lifecycle_state"] == "active"
    assert repository.payloads[str(point_id)]["ordinary_recall"] is True

    hypothesis_id = uuid4()
    repository.payloads[str(hypothesis_id)] = {
        "content": "private self model",
        "created_at": NOW.isoformat(),
        "lifecycle_state": "active",
        "ordinary_recall": False,
        "retention_directive": "keep",
        "record_class": "self_model_hypothesis",
    }
    private = {"id": str(hypothesis_id), **repository.payloads[str(hypothesis_id)]}
    untouched = path.process_exact_recall(private, kind="knowledge", now=NOW)
    assert untouched["ordinary_recall"] is False


def _trusted_identity() -> TrustedIdentityEvidence:
    return TrustedIdentityEvidence.from_authentication_boundary(
        scope=IdentityScope.from_values(agent="agent-a"),
        authentication_source="test-auth",
    )


def _prediction_pair(index: int) -> tuple[dict, dict]:
    prediction_id = uuid4()
    outcome_id = uuid4()
    session = f"session-{index % 4}"
    topic = ("deploy", "tests", "research")[index % 3]
    prediction = EpisodeRecord(
        id=prediction_id,
        content="Prediction: success",
        session_id=session,
        event_time=NOW - timedelta(hours=2),
        content_hash=f"{index:064x}"[-64:],
        agent="agent-a",
        project="CyberBrain",
        topic=topic,
        identity_trust=IdentityTrust.AUTHENTICATED,
        source="cognitive_prediction",
        context={
            "cognition": {
                "kind": "prediction",
                "prediction_id": str(prediction_id),
                "expected_outcome": "success",
                "confidence": 0.8,
                "strategy_tags": ["check-first"],
            }
        },
    )
    outcome = EpisodeRecord(
        id=outcome_id,
        content="Outcome: success",
        session_id=session,
        event_time=NOW - timedelta(hours=1),
        content_hash=f"{index + 1000:064x}"[-64:],
        agent="agent-a",
        project="CyberBrain",
        topic=topic,
        identity_trust=IdentityTrust.AUTHENTICATED,
        source="cognitive_outcome",
        context={
            "cognition": {
                "kind": "outcome",
                "prediction_id": str(prediction_id),
                "expected_outcome": "success",
                "prediction_confidence": 0.8,
                "observed_outcome": "success",
                "assessment": "confirmed",
                "prediction_error_class": "none",
                "confidence_weighted_error": 0.0,
            }
        },
    )
    return (
        {"id": str(prediction.id), "payload": prediction.model_dump(mode="json")},
        {"id": str(outcome.id), "payload": outcome.model_dump(mode="json")},
    )


def test_m6_active_run_auto_accepts_and_persists_when_readiness_is_met() -> None:
    repository = FakeRepository()
    for index in range(21):
        repository.points.extend(_prediction_pair(index))
    evolution = FakeEvolution()
    path = _path(repository, evolution)

    result = path.run_self_model(trusted_identity=_trusted_identity(), generated_at=NOW)

    assert result["status"] == "ready_read_only"
    assert result["generated"] > 0
    assert result["persisted"] == result["generated"]
    assert evolution.calls
    assert all(call["ordinary_recall"] is False for call in evolution.calls)
    assert all(call["record_class"].value == "self_model_hypothesis" for call in evolution.calls)
