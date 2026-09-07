# SPDX-License-Identifier: MPL-2.0
"""Prediction/outcome learning primitives backed by canonical Episodic Memory."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cyberbrain.memory.service import MemoryService
from cyberbrain.schemas.models import EpisodeRecord
from cyberbrain.storage.base import PointRepository


class PredictionAssessment(StrEnum):
    CONFIRMED = "confirmed"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    CONTRADICTED = "contradicted"
    INDETERMINATE = "indeterminate"


class PredictionErrorClass(StrEnum):
    NONE = "none"
    PARTIAL = "partial"
    FULL = "full"
    INDETERMINATE = "indeterminate"


class PredictionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_outcome: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0.0, le=1.0)
    action: str | None = Field(default=None, max_length=1000)
    rationale: str | None = Field(default=None, max_length=2000)

    @field_validator("expected_outcome", "action", "rationale")
    @classmethod
    def _strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized


class OutcomeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_outcome: str = Field(min_length=1, max_length=4000)
    assessment: PredictionAssessment

    @field_validator("observed_outcome")
    @classmethod
    def _strip_observed_outcome(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("observed_outcome must not be empty")
        return normalized


class PredictionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predictions_total: int
    outcomes_total: int
    resolved_predictions: int
    unresolved_predictions: int
    duplicate_outcomes: int
    mean_prediction_confidence: float | None
    mean_confidence_weighted_error: float | None
    assessment_counts: dict[str, int]
    error_class_counts: dict[str, int]
    may_be_truncated: bool
    sample_limit: int
    filters: dict[str, str]


class PredictionLearningService:
    """Record predictions and later outcomes without granting either truth authority."""

    def __init__(
        self,
        *,
        memory: MemoryService,
        repository: PointRepository,
        episodic_collection: str,
    ) -> None:
        self._memory = memory
        self._repository = repository
        self._episodic_collection = episodic_collection

    def record_prediction(
        self,
        *,
        expected_outcome: str,
        confidence: float,
        session_id: str,
        event_time: datetime,
        action: str | None = None,
        rationale: str | None = None,
        channel: str | None = None,
        agent: str | None = None,
        project: str | None = None,
        topic: str | None = None,
        keywords: list[str] | None = None,
        importance: str | None = None,
    ) -> EpisodeRecord:
        data = PredictionInput(
            expected_outcome=expected_outcome,
            confidence=confidence,
            action=action,
            rationale=rationale,
        )
        prediction_id = uuid4()
        cognition: dict[str, Any] = {
            "kind": "prediction",
            "prediction_id": str(prediction_id),
            "expected_outcome": data.expected_outcome,
            "confidence": data.confidence,
        }
        if data.action is not None:
            cognition["action"] = data.action
        if data.rationale is not None:
            cognition["rationale"] = data.rationale

        content = (
            f"Prediction for {data.action}: {data.expected_outcome}"
            if data.action
            else f"Prediction: {data.expected_outcome}"
        )
        return self._memory.store(
            content=content,
            session_id=session_id,
            event_time=event_time,
            channel=channel,
            agent=agent,
            project=project,
            topic=topic,
            keywords=keywords,
            importance=importance,
            source="cognitive_prediction",
            context={"cognition": cognition},
            point_id=prediction_id,
        )

    def record_outcome(
        self,
        *,
        prediction_id: UUID,
        observed_outcome: str,
        assessment: PredictionAssessment | str,
        event_time: datetime,
    ) -> EpisodeRecord:
        data = OutcomeInput(
            observed_outcome=observed_outcome,
            assessment=assessment,
        )
        prediction = self._load_prediction(prediction_id)
        prediction_cognition = self._prediction_cognition(prediction)
        if event_time.tzinfo is None or event_time.utcoffset() is None:
            raise ValueError("outcome event_time must include a timezone")
        if event_time < prediction.event_time:
            raise ValueError("outcome event_time must not precede prediction event_time")

        confidence = float(prediction_cognition["confidence"])
        error_class, error_value = self._derive_error(
            data.assessment,
            confidence=confidence,
        )
        cognition: dict[str, Any] = {
            "kind": "outcome",
            "prediction_id": str(prediction_id),
            "expected_outcome": str(prediction_cognition["expected_outcome"]),
            "prediction_confidence": confidence,
            "observed_outcome": data.observed_outcome,
            "assessment": data.assessment.value,
            "prediction_error_class": error_class.value,
            "confidence_weighted_error": error_value,
        }
        if prediction_cognition.get("action"):
            cognition["action"] = prediction_cognition["action"]

        return self._memory.store(
            content=f"Outcome: {data.observed_outcome}",
            session_id=prediction.session_id,
            event_time=event_time,
            channel=prediction.channel,
            agent=prediction.agent,
            project=prediction.project,
            topic=prediction.topic,
            keywords=list(prediction.keywords),
            importance=prediction.importance,
            source="cognitive_outcome",
            context={"cognition": cognition},
        )

    def observe(
        self,
        *,
        limit: int = 1000,
        session_id: str | None = None,
        agent: str | None = None,
        project: str | None = None,
        topic: str | None = None,
    ) -> PredictionObservation:
        if not 1 <= limit <= 10000:
            raise ValueError("prediction observation limit must be between 1 and 10000")

        filters = {
            key: value
            for key, value in {
                "session_id": session_id,
                "agent": agent,
                "project": project,
                "topic": topic,
            }.items()
            if value is not None
        }
        predictions = self._scroll_cognition(
            source="cognitive_prediction",
            limit=limit,
            filters=filters,
        )
        outcomes = self._scroll_cognition(
            source="cognitive_outcome",
            limit=limit,
            filters=filters,
        )

        prediction_rows: dict[str, tuple[EpisodeRecord, dict[str, Any]]] = {}
        for record, cognition in predictions:
            prediction_rows[str(record.id)] = (record, cognition)

        latest_outcomes: dict[str, tuple[EpisodeRecord, dict[str, Any]]] = {}
        outcome_counts: dict[str, int] = {}
        for record, cognition in outcomes:
            prediction_id = str(cognition.get("prediction_id") or "")
            if prediction_id not in prediction_rows:
                continue
            outcome_counts[prediction_id] = outcome_counts.get(prediction_id, 0) + 1
            current = latest_outcomes.get(prediction_id)
            if current is None or record.event_time > current[0].event_time:
                latest_outcomes[prediction_id] = (record, cognition)

        confidences = [
            float(cognition["confidence"])
            for _record, cognition in prediction_rows.values()
            if isinstance(cognition.get("confidence"), int | float)
        ]
        weighted_errors: list[float] = []
        assessment_counts = {item.value: 0 for item in PredictionAssessment}
        error_class_counts = {item.value: 0 for item in PredictionErrorClass}

        for _record, cognition in latest_outcomes.values():
            assessment = str(cognition.get("assessment") or "")
            if assessment in assessment_counts:
                assessment_counts[assessment] += 1
            error_class = str(cognition.get("prediction_error_class") or "")
            if error_class in error_class_counts:
                error_class_counts[error_class] += 1
            weighted_error = cognition.get("confidence_weighted_error")
            if isinstance(weighted_error, int | float):
                weighted_errors.append(float(weighted_error))

        resolved = len(latest_outcomes)
        duplicate_outcomes = sum(max(0, count - 1) for count in outcome_counts.values())
        return PredictionObservation(
            predictions_total=len(prediction_rows),
            outcomes_total=len(outcomes),
            resolved_predictions=resolved,
            unresolved_predictions=max(0, len(prediction_rows) - resolved),
            duplicate_outcomes=duplicate_outcomes,
            mean_prediction_confidence=self._mean(confidences),
            mean_confidence_weighted_error=self._mean(weighted_errors),
            assessment_counts=assessment_counts,
            error_class_counts=error_class_counts,
            may_be_truncated=len(predictions) >= limit or len(outcomes) >= limit,
            sample_limit=limit,
            filters=dict(filters),
        )

    def _scroll_cognition(
        self,
        *,
        source: str,
        limit: int,
        filters: dict[str, str],
    ) -> list[tuple[EpisodeRecord, dict[str, Any]]]:
        conditions = [{"key": "source", "match": {"value": source}}]
        conditions.extend(
            {"key": key, "match": {"value": value}}
            for key, value in filters.items()
        )
        points = self._repository.scroll(
            self._episodic_collection,
            qdrant_filter={"must": conditions},
            limit=limit,
        )
        result: list[tuple[EpisodeRecord, dict[str, Any]]] = []
        expected_kind = "prediction" if source == "cognitive_prediction" else "outcome"
        for point in points:
            payload = point.get("payload") or {}
            try:
                record = EpisodeRecord.model_validate(payload)
            except Exception:
                continue
            cognition = record.context.get("cognition")
            if not isinstance(cognition, dict) or cognition.get("kind") != expected_kind:
                continue
            result.append((record, cognition))
        return result

    @staticmethod
    def _mean(values: list[float]) -> float | None:
        if not values:
            return None
        return round(sum(values) / len(values), 6)

    def _load_prediction(self, prediction_id: UUID) -> EpisodeRecord:
        point = self._repository.retrieve(
            self._episodic_collection,
            point_id=prediction_id,
        )
        if point is None:
            raise ValueError(f"prediction not found: {prediction_id}")
        payload = point.get("payload") or {}
        try:
            record = EpisodeRecord.model_validate(payload)
        except Exception as exc:
            raise ValueError("prediction record is not a valid canonical episode") from exc
        self._prediction_cognition(record)
        return record

    @staticmethod
    def _prediction_cognition(record: EpisodeRecord) -> dict[str, Any]:
        cognition = record.context.get("cognition")
        if not isinstance(cognition, dict) or cognition.get("kind") != "prediction":
            raise ValueError(f"episode is not a prediction: {record.id}")
        if str(cognition.get("prediction_id") or "") != str(record.id):
            raise ValueError("prediction provenance id does not match episode id")
        expected = str(cognition.get("expected_outcome") or "").strip()
        confidence = cognition.get("confidence")
        if not expected:
            raise ValueError("prediction is missing expected_outcome")
        if not isinstance(confidence, int | float) or not 0 <= float(confidence) <= 1:
            raise ValueError("prediction confidence is invalid")
        return cognition

    @staticmethod
    def _derive_error(
        assessment: PredictionAssessment,
        *,
        confidence: float,
    ) -> tuple[PredictionErrorClass, float | None]:
        if assessment is PredictionAssessment.CONFIRMED:
            return PredictionErrorClass.NONE, 0.0
        if assessment is PredictionAssessment.PARTIALLY_CONFIRMED:
            return PredictionErrorClass.PARTIAL, round(confidence * 0.5, 6)
        if assessment is PredictionAssessment.CONTRADICTED:
            return PredictionErrorClass.FULL, round(confidence, 6)
        return PredictionErrorClass.INDETERMINATE, None
