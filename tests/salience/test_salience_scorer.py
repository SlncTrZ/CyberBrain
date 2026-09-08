# SPDX-License-Identifier: MPL-2.0

import random
import time

import pytest

from cyberbrain.salience import (
    SALIENCE_ASSESSMENT_VERSION,
    SalienceConfig,
    SalienceInput,
    SalienceReasonCode,
    SalienceScorer,
)

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


def test_assessment_is_deterministic() -> None:
    scorer = SalienceScorer(SalienceConfig())
    item = SalienceInput(
        prediction_error=0.8,
        contradiction=0.5,
        novelty=0.25,
        user_emphasis=1.0,
    )

    first = scorer.assess(item)
    second = scorer.assess(item)

    assert first == second


def test_all_missing_is_neutral_without_fabricated_reasons() -> None:
    result = SalienceScorer(SalienceConfig()).assess(SalienceInput())

    assert result.score == 0.0
    assert result.reason_codes == ()
    assert result.normalized_signals == ()
    assert result.assessment_version == SALIENCE_ASSESSMENT_VERSION


def test_all_zero_is_neutral_without_fabricated_reasons() -> None:
    item = SalienceInput(**dict.fromkeys(_SIGNAL_NAMES, 0.0))

    result = SalienceScorer(SalienceConfig()).assess(item)

    assert result.score == 0.0
    assert result.reason_codes == ()
    assert result.normalized_signals == tuple((name, 0.0) for name in _SIGNAL_NAMES)


@pytest.mark.parametrize("signal_name", _SIGNAL_NAMES)
def test_each_signal_is_monotonic(signal_name: str) -> None:
    base = dict.fromkeys(_SIGNAL_NAMES, 0.25)
    higher = dict(base)
    higher[signal_name] = 0.75
    scorer = SalienceScorer(SalienceConfig())

    lower_score = scorer.assess(SalienceInput(**base)).score
    higher_score = scorer.assess(SalienceInput(**higher)).score

    assert higher_score >= lower_score


def test_weighted_formula_is_inspectable_and_uses_present_signals_only() -> None:
    config = SalienceConfig(
        prediction_error=2.0,
        unresolvedness=1.0,
        contradiction=0.0,
        novelty=0.0,
        recurrence=0.0,
        consequence=0.0,
        user_emphasis=0.0,
        recency=0.0,
    )
    item = SalienceInput(prediction_error=0.8, unresolvedness=0.2)
    result = SalienceScorer(config).assess(item)

    assert result.score == pytest.approx(0.6)
    assert result.normalized_signals == (
        ("prediction_error", 0.8),
        ("unresolvedness", 0.2),
    )


def test_reason_codes_have_stable_domain_order() -> None:
    item = SalienceInput(
        recency=0.4,
        contradiction=0.7,
        prediction_error=0.2,
        user_emphasis=1.0,
    )

    result = SalienceScorer(SalienceConfig()).assess(item)

    assert result.reason_codes == (
        SalienceReasonCode.PREDICTION_ERROR,
        SalienceReasonCode.CONTRADICTION,
        SalienceReasonCode.USER_EMPHASIS,
        SalienceReasonCode.RECENCY,
    )


def test_missing_signal_never_invents_reason_or_normalized_value() -> None:
    result = SalienceScorer(SalienceConfig()).assess(SalienceInput(novelty=0.5))

    assert result.reason_codes == (SalienceReasonCode.NOVELTY,)
    assert result.normalized_signals == (("novelty", 0.5),)


def test_zero_weight_signal_is_not_considered() -> None:
    config = SalienceConfig(
        prediction_error=0.0,
        unresolvedness=0.0,
        contradiction=0.0,
        novelty=1.0,
        recurrence=0.0,
        consequence=0.0,
        user_emphasis=0.0,
        recency=0.0,
    )

    result = SalienceScorer(config).assess(
        SalienceInput(prediction_error=1.0, novelty=0.25)
    )

    assert result.score == 0.25
    assert result.reason_codes == (SalienceReasonCode.NOVELTY,)
    assert result.normalized_signals == (("novelty", 0.25),)


def test_full_scale_input_is_bounded() -> None:
    item = SalienceInput(**dict.fromkeys(_SIGNAL_NAMES, 1.0))

    result = SalienceScorer(SalienceConfig()).assess(item)

    assert result.score == 1.0
    assert 0.0 <= result.score <= 1.0


def test_very_large_finite_weights_cannot_overflow_score() -> None:
    config = SalienceConfig(**dict.fromkeys(_SIGNAL_NAMES, 1e308))
    item = SalienceInput(**dict.fromkeys(_SIGNAL_NAMES, 1.0))

    result = SalienceScorer(config).assess(item)

    assert result.score == 1.0


def test_assessment_does_not_depend_on_process_time_or_randomness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scorer = SalienceScorer(SalienceConfig())
    item = SalienceInput(consequence=0.75, recency=0.25)
    expected = scorer.assess(item)

    def fail_hidden_dependency() -> float:
        raise AssertionError("salience scorer must not read process time or randomness")

    monkeypatch.setattr(time, "time", fail_hidden_dependency)
    monkeypatch.setattr(random, "random", fail_hidden_dependency)

    assert scorer.assess(item) == expected
