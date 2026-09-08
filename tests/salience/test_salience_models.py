# SPDX-License-Identifier: MPL-2.0

from dataclasses import FrozenInstanceError

import pytest

from cyberbrain.salience import SalienceAssessment, SalienceConfig, SalienceInput

_SIGNAL_NAMES = (
    "prediction_error",
    "unresolvedness",
    "contradiction",
    "novelty",
    "recurrence",
    "consequence",
    "user_emphasis",
    "recency",
)


@pytest.mark.parametrize("signal_name", _SIGNAL_NAMES)
@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf"), -0.01, 1.01])
def test_salience_input_rejects_invalid_signal_values(
    signal_name: str,
    invalid: float,
) -> None:
    with pytest.raises(ValueError):
        SalienceInput(**{signal_name: invalid})


@pytest.mark.parametrize("signal_name", _SIGNAL_NAMES)
def test_salience_input_normalizes_numeric_signals_to_float(signal_name: str) -> None:
    item = SalienceInput(**{signal_name: 1})

    assert getattr(item, signal_name) == 1.0
    assert isinstance(getattr(item, signal_name), float)


@pytest.mark.parametrize("signal_name", _SIGNAL_NAMES)
@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf"), -0.01])
def test_salience_config_rejects_invalid_weights(signal_name: str, invalid: float) -> None:
    with pytest.raises(ValueError):
        SalienceConfig(**{signal_name: invalid})


def test_salience_config_requires_at_least_one_positive_weight() -> None:
    with pytest.raises(ValueError, match="at least one positive weight"):
        SalienceConfig(**dict.fromkeys(_SIGNAL_NAMES, 0.0))


def test_models_reject_boolean_numbers() -> None:
    with pytest.raises(ValueError):
        SalienceInput(novelty=True)

    with pytest.raises(ValueError):
        SalienceConfig(novelty=True)


def test_input_has_no_arbitrary_metadata_channel() -> None:
    with pytest.raises(TypeError):
        SalienceInput(metadata={"ignored": "value"})


def test_input_and_assessment_are_immutable() -> None:
    item = SalienceInput(novelty=0.5)
    assessment = SalienceAssessment(
        score=0.5,
        reason_codes=(),
        normalized_signals=(("novelty", 0.5),),
        assessment_version="test-contract",
    )

    with pytest.raises(FrozenInstanceError):
        item.novelty = 0.75

    with pytest.raises(FrozenInstanceError):
        assessment.score = 0.75
