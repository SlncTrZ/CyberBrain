# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import pytest

from cyberbrain.cognition.calibration import (
    CalibrationAssessment,
    MetacognitionCalibrationService,
)


class FakePredictionLearning:
    def __init__(
        self,
        *,
        samples: list[dict[str, float]],
        excluded_indeterminate: int = 0,
        may_be_incomplete: bool = False,
    ) -> None:
        self.samples = samples
        self.excluded_indeterminate = excluded_indeterminate
        self.may_be_incomplete = may_be_incomplete
        self.calls: list[dict] = []

    def calibration_samples(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.samples, self.excluded_indeterminate, self.may_be_incomplete


def test_calibration_requires_minimum_evidence_before_classification() -> None:
    prediction_learning = FakePredictionLearning(
        samples=[
            {"confidence": 0.95, "empirical_score": 0.0},
            {"confidence": 0.9, "empirical_score": 0.0},
        ]
    )
    service = MetacognitionCalibrationService(
        prediction_learning=prediction_learning,
    )

    report = service.observe(minimum_samples=3)

    assert report.usable_samples == 2
    assert report.calibration_bias == 0.925
    assert report.assessment == CalibrationAssessment.INSUFFICIENT_EVIDENCE


def test_calibration_detects_overconfidence_after_minimum_samples() -> None:
    prediction_learning = FakePredictionLearning(
        samples=[
            {"confidence": 0.9, "empirical_score": 0.0},
            {"confidence": 0.8, "empirical_score": 0.5},
            {"confidence": 0.7, "empirical_score": 0.0},
        ]
    )
    service = MetacognitionCalibrationService(
        prediction_learning=prediction_learning,
    )

    report = service.observe(minimum_samples=3, bias_threshold=0.1)

    assert report.mean_confidence == 0.8
    assert report.mean_empirical_score == pytest.approx(1 / 6, abs=1e-6)
    assert report.calibration_bias == pytest.approx(0.633333, abs=1e-6)
    assert report.mean_squared_calibration_error == pytest.approx(
        (0.9**2 + 0.3**2 + 0.7**2) / 3,
        abs=1e-6,
    )
    assert report.assessment == CalibrationAssessment.OVERCONFIDENT


def test_calibration_detects_underconfidence() -> None:
    prediction_learning = FakePredictionLearning(
        samples=[
            {"confidence": 0.2, "empirical_score": 1.0},
            {"confidence": 0.3, "empirical_score": 1.0},
            {"confidence": 0.4, "empirical_score": 0.5},
        ]
    )
    service = MetacognitionCalibrationService(
        prediction_learning=prediction_learning,
    )

    report = service.observe(minimum_samples=3, bias_threshold=0.1)

    assert report.calibration_bias == pytest.approx(-0.533333, abs=1e-6)
    assert report.assessment == CalibrationAssessment.UNDERCONFIDENT


def test_calibration_detects_roughly_calibrated_sample() -> None:
    prediction_learning = FakePredictionLearning(
        samples=[
            {"confidence": 0.9, "empirical_score": 1.0},
            {"confidence": 0.6, "empirical_score": 0.5},
            {"confidence": 0.1, "empirical_score": 0.0},
        ]
    )
    service = MetacognitionCalibrationService(
        prediction_learning=prediction_learning,
    )

    report = service.observe(minimum_samples=3, bias_threshold=0.11)

    assert report.calibration_bias == pytest.approx(0.033333, abs=1e-6)
    assert report.assessment == CalibrationAssessment.ROUGHLY_CALIBRATED


def test_calibration_reports_excluded_indeterminate_and_truncation() -> None:
    prediction_learning = FakePredictionLearning(
        samples=[],
        excluded_indeterminate=4,
        may_be_incomplete=True,
    )
    service = MetacognitionCalibrationService(
        prediction_learning=prediction_learning,
    )

    report = service.observe(
        project="Project A",
        agent="agent-a",
        limit=50,
    )

    assert report.usable_samples == 0
    assert report.excluded_indeterminate == 4
    assert report.may_be_incomplete is True
    assert report.assessment == CalibrationAssessment.INSUFFICIENT_EVIDENCE
    assert report.filters == {
        "agent": "agent-a",
        "project": "Project A",
    }
    assert prediction_learning.calls[-1] == {
        "limit": 50,
        "agent": "agent-a",
        "project": "Project A",
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": 0}, "calibration limit"),
        ({"minimum_samples": 0}, "minimum_samples"),
        ({"bias_threshold": 1.1}, "bias_threshold"),
    ],
)
def test_calibration_rejects_invalid_parameters(kwargs, message) -> None:
    service = MetacognitionCalibrationService(
        prediction_learning=FakePredictionLearning(samples=[]),
    )

    with pytest.raises(ValueError, match=message):
        service.observe(**kwargs)
