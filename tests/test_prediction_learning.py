# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from cyberbrain.cognition.prediction import (
    PredictionAssessment,
    PredictionErrorClass,
    PredictionLearningService,
)
from cyberbrain.dreaming.retriever import QdrantEvidenceRetriever
from cyberbrain.memory.service import MemoryService


class FakeEmbedding:
    dimension = 3
    version = "fake@v1"

    def embed(self, text: str) -> list[float]:
        del text
        return [0.1, 0.2, 0.3]


class FakeRepository:
    def __init__(self) -> None:
        self.points: dict[UUID, dict[str, Any]] = {}

    def upsert(
        self,
        collection: str,
        *,
        point_id: UUID,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        del collection
        self.points[point_id] = {
            "id": str(point_id),
            "vector": vector,
            "payload": payload,
        }

    def set_payload(
        self,
        collection: str,
        *,
        point_id: UUID,
        payload: dict[str, Any],
    ) -> None:
        del collection
        self.points[point_id]["payload"].update(payload)

    def retrieve(
        self,
        collection: str,
        point_id: UUID,
    ) -> dict[str, Any] | None:
        del collection
        return self.points.get(point_id)

    def search(
        self,
        collection: str,
        *,
        vector: list[float],
        limit: int,
        qdrant_filter: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        del collection, vector, qdrant_filter, score_threshold
        return [
            {
                "id": point["id"],
                "score": 0.9,
                "payload": point["payload"],
            }
            for point in list(self.points.values())[:limit]
        ]

    def scroll(
        self,
        collection: str,
        *,
        qdrant_filter: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        del collection
        conditions = (qdrant_filter or {}).get("must", [])

        def matches(point: dict[str, Any]) -> bool:
            payload = point["payload"]
            for condition in conditions:
                key = str(condition["key"])
                expected = condition["match"]["value"]
                if payload.get(key) != expected:
                    return False
            return True

        return [
            {"id": point["id"], "payload": point["payload"]}
            for point in self.points.values()
            if matches(point)
        ][:limit]


@pytest.fixture
def learning() -> tuple[PredictionLearningService, MemoryService, FakeRepository]:
    repository = FakeRepository()
    memory = MemoryService(
        repository=repository,
        embedding=FakeEmbedding(),
        collection="cyberbrain_episodic",
    )
    service = PredictionLearningService(
        memory=memory,
        repository=repository,
        episodic_collection="cyberbrain_episodic",
    )
    return service, memory, repository


def test_prediction_is_canonical_episode_with_self_provenance(learning) -> None:
    service, _memory, _repository = learning
    event_time = datetime(2026, 9, 7, 1, 0, tzinfo=UTC)

    record = service.record_prediction(
        expected_outcome="The validation suite will pass.",
        confidence=0.8,
        action="run release validation",
        rationale="Targeted tests already passed.",
        session_id="session-1",
        event_time=event_time,
        agent="agent-a",
        project="CyberBrain",
        topic="release",
    )

    cognition = record.context["cognition"]
    assert record.source == "cognitive_prediction"
    assert cognition["kind"] == "prediction"
    assert cognition["prediction_id"] == str(record.id)
    assert cognition["expected_outcome"] == "The validation suite will pass."
    assert cognition["confidence"] == 0.8
    assert cognition["action"] == "run release validation"
    assert record.session_id == "session-1"


@pytest.mark.parametrize(
    ("assessment", "error_class", "error_value"),
    [
        (PredictionAssessment.CONFIRMED, PredictionErrorClass.NONE, 0.0),
        (PredictionAssessment.PARTIALLY_CONFIRMED, PredictionErrorClass.PARTIAL, 0.4),
        (PredictionAssessment.CONTRADICTED, PredictionErrorClass.FULL, 0.8),
        (PredictionAssessment.INDETERMINATE, PredictionErrorClass.INDETERMINATE, None),
    ],
)
def test_outcome_derives_confidence_weighted_prediction_error(
    learning,
    assessment: PredictionAssessment,
    error_class: PredictionErrorClass,
    error_value: float | None,
) -> None:
    service, _memory, _repository = learning
    prediction = service.record_prediction(
        expected_outcome="Deployment will start cleanly.",
        confidence=0.8,
        session_id="session-1",
        event_time=datetime(2026, 9, 7, 1, 0, tzinfo=UTC),
        agent="agent-a",
        project="CyberBrain",
        topic="deployment",
    )

    outcome = service.record_outcome(
        prediction_id=prediction.id,
        observed_outcome="Observed deployment result.",
        assessment=assessment,
        event_time=datetime(2026, 9, 7, 1, 5, tzinfo=UTC),
    )

    cognition = outcome.context["cognition"]
    assert cognition["prediction_id"] == str(prediction.id)
    assert cognition["assessment"] == assessment.value
    assert cognition["prediction_error_class"] == error_class.value
    assert cognition["confidence_weighted_error"] == error_value


def test_outcome_inherits_prediction_identity_context(learning) -> None:
    service, _memory, _repository = learning
    prediction = service.record_prediction(
        expected_outcome="The task completes.",
        confidence=0.65,
        session_id="session-origin",
        event_time=datetime(2026, 9, 7, 1, 0, tzinfo=UTC),
        channel="mcp",
        agent="agent-origin",
        project="Project A",
        topic="task",
        keywords=["prediction", "task"],
        importance="high",
    )

    outcome = service.record_outcome(
        prediction_id=prediction.id,
        observed_outcome="The task failed.",
        assessment="contradicted",
        event_time=datetime(2026, 9, 7, 1, 10, tzinfo=UTC),
    )

    assert outcome.session_id == prediction.session_id
    assert outcome.channel == prediction.channel
    assert outcome.agent == prediction.agent
    assert outcome.project == prediction.project
    assert outcome.topic == prediction.topic
    assert outcome.keywords == prediction.keywords
    assert outcome.importance == prediction.importance
    assert outcome.source == "cognitive_outcome"


def test_resolve_rejects_non_prediction_episode(learning) -> None:
    service, memory, _repository = learning
    ordinary = memory.store(
        content="ordinary observation",
        session_id="session-1",
        event_time=datetime(2026, 9, 7, 1, 0, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="not a prediction"):
        service.record_outcome(
            prediction_id=ordinary.id,
            observed_outcome="nothing to resolve",
            assessment="indeterminate",
            event_time=datetime(2026, 9, 7, 1, 5, tzinfo=UTC),
        )


def test_resolve_rejects_unknown_prediction(learning) -> None:
    service, _memory, _repository = learning

    with pytest.raises(ValueError, match="prediction not found"):
        service.record_outcome(
            prediction_id=uuid4(),
            observed_outcome="unknown",
            assessment="indeterminate",
            event_time=datetime(2026, 9, 7, 1, 5, tzinfo=UTC),
        )


def test_prediction_confidence_must_be_bounded(learning) -> None:
    service, _memory, _repository = learning

    with pytest.raises(ValueError):
        service.record_prediction(
            expected_outcome="Impossible confidence.",
            confidence=1.1,
            session_id="session-1",
            event_time=datetime(2026, 9, 7, 1, 0, tzinfo=UTC),
        )


def test_dreaming_evidence_preserves_cognition_context(learning) -> None:
    service, _memory, repository = learning
    prediction = service.record_prediction(
        expected_outcome="A check will pass.",
        confidence=0.7,
        session_id="session-1",
        event_time=datetime(2026, 9, 7, 1, 0, tzinfo=UTC),
        topic="validation",
    )
    outcome = service.record_outcome(
        prediction_id=prediction.id,
        observed_outcome="The check failed.",
        assessment="contradicted",
        event_time=datetime(2026, 9, 7, 1, 5, tzinfo=UTC),
    )

    point = repository.retrieve("cyberbrain_episodic", outcome.id)
    assert point is not None
    evidence = QdrantEvidenceRetriever._to_evidence(point, record_type="episode")

    assert evidence is not None
    cognition = evidence.metadata["context"]["cognition"]
    assert cognition["kind"] == "outcome"
    assert cognition["prediction_id"] == str(prediction.id)
    assert cognition["prediction_error_class"] == "full"


def test_outcome_cannot_precede_prediction(learning) -> None:
    service, _memory, _repository = learning
    start = datetime(2026, 9, 7, 1, 0, tzinfo=UTC)
    prediction = service.record_prediction(
        expected_outcome="The action completes.",
        confidence=0.6,
        session_id="session-1",
        event_time=start,
    )

    with pytest.raises(ValueError, match="must not precede"):
        service.record_outcome(
            prediction_id=prediction.id,
            observed_outcome="Impossible earlier result.",
            assessment="indeterminate",
            event_time=start - timedelta(seconds=1),
        )


def test_observe_summarizes_latest_outcome_per_prediction(learning) -> None:
    service, _memory, _repository = learning
    start = datetime(2026, 9, 7, 1, 0, tzinfo=UTC)

    first = service.record_prediction(
        expected_outcome="First prediction succeeds.",
        confidence=0.8,
        session_id="session-1",
        event_time=start,
        agent="agent-a",
        project="Project A",
        topic="validation",
    )
    second = service.record_prediction(
        expected_outcome="Second prediction succeeds.",
        confidence=0.4,
        session_id="session-1",
        event_time=start + timedelta(minutes=1),
        agent="agent-a",
        project="Project A",
        topic="validation",
    )
    service.record_outcome(
        prediction_id=first.id,
        observed_outcome="First result failed.",
        assessment="contradicted",
        event_time=start + timedelta(minutes=2),
    )
    service.record_outcome(
        prediction_id=first.id,
        observed_outcome="Later evidence partially confirmed the expectation.",
        assessment="partially_confirmed",
        event_time=start + timedelta(minutes=3),
    )

    observation = service.observe(project="Project A")

    assert observation.predictions_total == 2
    assert observation.outcomes_total == 2
    assert observation.resolved_predictions == 1
    assert observation.unresolved_predictions == 1
    assert observation.duplicate_outcomes == 1
    assert observation.mean_prediction_confidence == 0.6
    assert observation.assessment_counts["partially_confirmed"] == 1
    assert observation.assessment_counts["contradicted"] == 0
    assert observation.error_class_counts["partial"] == 1
    assert observation.mean_confidence_weighted_error == 0.4
    assert observation.filters == {"project": "Project A"}
    assert second.id != first.id


def test_observe_filters_prediction_population(learning) -> None:
    service, _memory, _repository = learning
    start = datetime(2026, 9, 7, 1, 0, tzinfo=UTC)

    service.record_prediction(
        expected_outcome="Project A prediction.",
        confidence=0.7,
        session_id="session-a",
        event_time=start,
        agent="agent-a",
        project="Project A",
        topic="release",
    )
    service.record_prediction(
        expected_outcome="Project B prediction.",
        confidence=0.9,
        session_id="session-b",
        event_time=start,
        agent="agent-b",
        project="Project B",
        topic="release",
    )

    observation = service.observe(
        session_id="session-a",
        agent="agent-a",
        project="Project A",
        topic="release",
    )

    assert observation.predictions_total == 1
    assert observation.unresolved_predictions == 1
    assert observation.mean_prediction_confidence == 0.7
    assert observation.filters == {
        "session_id": "session-a",
        "agent": "agent-a",
        "project": "Project A",
        "topic": "release",
    }


def test_observe_marks_possible_truncation(learning) -> None:
    service, _memory, _repository = learning
    service.record_prediction(
        expected_outcome="One prediction.",
        confidence=0.5,
        session_id="session-1",
        event_time=datetime(2026, 9, 7, 1, 0, tzinfo=UTC),
    )

    observation = service.observe(limit=1)

    assert observation.may_be_truncated is True
    assert observation.sample_limit == 1


def test_observe_rejects_invalid_limit(learning) -> None:
    service, _memory, _repository = learning

    with pytest.raises(ValueError, match="between 1 and 10000"):
        service.observe(limit=0)


def test_pending_lists_only_unresolved_predictions_in_time_order(learning) -> None:
    service, _memory, _repository = learning
    start = datetime(2026, 9, 7, 1, 0, tzinfo=UTC)

    first = service.record_prediction(
        expected_outcome="First unresolved prediction.",
        confidence=0.6,
        session_id="session-1",
        event_time=start,
        agent="agent-a",
        project="Project A",
        topic="validation",
    )
    resolved = service.record_prediction(
        expected_outcome="Resolved prediction.",
        confidence=0.8,
        session_id="session-1",
        event_time=start + timedelta(minutes=1),
        agent="agent-a",
        project="Project A",
        topic="validation",
    )
    second = service.record_prediction(
        expected_outcome="Second unresolved prediction.",
        confidence=0.7,
        session_id="session-1",
        event_time=start + timedelta(minutes=2),
        agent="agent-a",
        project="Project A",
        topic="validation",
    )
    service.record_outcome(
        prediction_id=resolved.id,
        observed_outcome="Resolved.",
        assessment="confirmed",
        event_time=start + timedelta(minutes=3),
    )

    pending = service.pending(project="Project A")

    assert [item.prediction_id for item in pending.items] == [first.id, second.id]
    assert pending.returned == 2
    assert pending.may_be_incomplete is False
    assert pending.filters == {"project": "Project A"}


def test_pending_respects_filters_and_result_limit(learning) -> None:
    service, _memory, _repository = learning
    start = datetime(2026, 9, 7, 1, 0, tzinfo=UTC)

    service.record_prediction(
        expected_outcome="Agent A prediction 1.",
        confidence=0.6,
        session_id="session-a",
        event_time=start,
        agent="agent-a",
        project="Project A",
        topic="release",
    )
    service.record_prediction(
        expected_outcome="Agent A prediction 2.",
        confidence=0.7,
        session_id="session-a",
        event_time=start + timedelta(minutes=1),
        agent="agent-a",
        project="Project A",
        topic="release",
    )
    service.record_prediction(
        expected_outcome="Agent B prediction.",
        confidence=0.9,
        session_id="session-b",
        event_time=start,
        agent="agent-b",
        project="Project B",
        topic="release",
    )

    pending = service.pending(
        session_id="session-a",
        agent="agent-a",
        project="Project A",
        topic="release",
        limit=1,
    )

    assert pending.returned == 1
    assert pending.items[0].session_id == "session-a"
    assert pending.items[0].agent == "agent-a"
    assert pending.filters == {
        "session_id": "session-a",
        "agent": "agent-a",
        "project": "Project A",
        "topic": "release",
    }


def test_pending_marks_incomplete_when_scan_limit_is_reached(learning) -> None:
    service, _memory, _repository = learning
    service.record_prediction(
        expected_outcome="One prediction.",
        confidence=0.5,
        session_id="session-1",
        event_time=datetime(2026, 9, 7, 1, 0, tzinfo=UTC),
    )

    pending = service.pending(scan_limit=1)

    assert pending.may_be_incomplete is True
    assert pending.scan_limit == 1


def test_pending_rejects_invalid_limits(learning) -> None:
    service, _memory, _repository = learning

    with pytest.raises(ValueError, match="pending limit"):
        service.pending(limit=0)
    with pytest.raises(ValueError, match="scan limit"):
        service.pending(scan_limit=0)


def test_outcome_can_occur_later_than_prediction(learning) -> None:
    service, _memory, _repository = learning
    start = datetime(2026, 9, 7, 1, 0, tzinfo=UTC)
    prediction = service.record_prediction(
        expected_outcome="The scheduled action will complete.",
        confidence=0.6,
        session_id="session-1",
        event_time=start,
    )

    outcome = service.record_outcome(
        prediction_id=prediction.id,
        observed_outcome="The scheduled action completed.",
        assessment="confirmed",
        event_time=start + timedelta(days=1),
    )

    assert outcome.event_time > prediction.event_time
