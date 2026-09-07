# SPDX-License-Identifier: MPL-2.0
"""Read-only metacognition/calibration analysis over Prediction Learning evidence."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from cyberbrain.cognition.prediction import PredictionLearningService


class CalibrationAssessment(StrEnum):
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    ROUGHLY_CALIBRATED = "roughly_calibrated"
    OVERCONFIDENT = "overconfident"
    UNDERCONFIDENT = "underconfident"


class CalibrationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usable_samples: int
    excluded_indeterminate: int
    minimum_samples: int
    mean_confidence: float | None
    mean_empirical_score: float | None
    calibration_bias: float | None
    mean_squared_calibration_error: float | None
    assessment: CalibrationAssessment
    bias_threshold: float
    may_be_incomplete: bool
    filters: dict[str, str]


class MetacognitionCalibrationService:
    """Analyze confidence calibration without mutating Memory, Knowledge, or agent identity."""

    def __init__(self, *, prediction_learning: PredictionLearningService) -> None:
        self._prediction_learning = prediction_learning

    def observe(
        self,
        *,
        limit: int = 1000,
        minimum_samples: int = 20,
        bias_threshold: float = 0.1,
        session_id: str | None = None,
        agent: str | None = None,
        project: str | None = None,
        topic: str | None = None,
    ) -> CalibrationReport:
        if not 1 <= limit <= 10000:
            raise ValueError("calibration limit must be between 1 and 10000")
        if not 1 <= minimum_samples <= 10000:
            raise ValueError("minimum_samples must be between 1 and 10000")
        if not 0 <= bias_threshold <= 1:
            raise ValueError("bias_threshold must be between 0 and 1")

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
        samples, excluded_indeterminate, may_be_incomplete = (
            self._prediction_learning.calibration_samples(
                limit=limit,
                **filters,
            )
        )

        usable = len(samples)
        if usable == 0:
            return CalibrationReport(
                usable_samples=0,
                excluded_indeterminate=excluded_indeterminate,
                minimum_samples=minimum_samples,
                mean_confidence=None,
                mean_empirical_score=None,
                calibration_bias=None,
                mean_squared_calibration_error=None,
                assessment=CalibrationAssessment.INSUFFICIENT_EVIDENCE,
                bias_threshold=bias_threshold,
                may_be_incomplete=may_be_incomplete,
                filters=filters,
            )

        confidences = [sample["confidence"] for sample in samples]
        empirical = [sample["empirical_score"] for sample in samples]
        biases = [
            confidence - empirical_score
            for confidence, empirical_score in zip(confidences, empirical, strict=True)
        ]
        squared_errors = [value * value for value in biases]
        mean_confidence = self._mean(confidences)
        mean_empirical = self._mean(empirical)
        calibration_bias = self._mean(biases)
        squared_error = self._mean(squared_errors)

        assessment = CalibrationAssessment.INSUFFICIENT_EVIDENCE
        if usable >= minimum_samples:
            assert calibration_bias is not None
            if calibration_bias > bias_threshold:
                assessment = CalibrationAssessment.OVERCONFIDENT
            elif calibration_bias < -bias_threshold:
                assessment = CalibrationAssessment.UNDERCONFIDENT
            else:
                assessment = CalibrationAssessment.ROUGHLY_CALIBRATED

        return CalibrationReport(
            usable_samples=usable,
            excluded_indeterminate=excluded_indeterminate,
            minimum_samples=minimum_samples,
            mean_confidence=mean_confidence,
            mean_empirical_score=mean_empirical,
            calibration_bias=calibration_bias,
            mean_squared_calibration_error=squared_error,
            assessment=assessment,
            bias_threshold=bias_threshold,
            may_be_incomplete=may_be_incomplete,
            filters=filters,
        )

    @staticmethod
    def _mean(values: list[float]) -> float | None:
        if not values:
            return None
        return round(sum(values) / len(values), 6)
