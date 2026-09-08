# SPDX-License-Identifier: MPL-2.0
"""Immutable domain models for deterministic salience assessment."""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from enum import StrEnum


class SalienceReasonCode(StrEnum):
    """Stable, content-free reasons for positive salience contributions."""

    PREDICTION_ERROR = "prediction_error"
    UNRESOLVEDNESS = "unresolvedness"
    CONTRADICTION = "contradiction"
    NOVELTY = "novelty"
    RECURRENCE = "recurrence"
    CONSEQUENCE = "consequence"
    USER_EMPHASIS = "user_emphasis"
    RECENCY = "recency"


@dataclass(frozen=True, slots=True)
class SalienceInput:
    """Explicit bounded salience signals; missing values remain unknown."""

    prediction_error: float | None = None
    unresolvedness: float | None = None
    contradiction: float | None = None
    novelty: float | None = None
    recurrence: float | None = None
    consequence: float | None = None
    user_emphasis: float | None = None
    recency: float | None = None

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if value is None:
                continue
            object.__setattr__(
                self,
                item.name,
                _validated_number(item.name, value, minimum=0.0, maximum=1.0),
            )


@dataclass(frozen=True, slots=True)
class SalienceConfig:
    """Explicit non-negative weights for the M3.1 salience signals."""

    prediction_error: float = 1.0
    unresolvedness: float = 1.0
    contradiction: float = 1.0
    novelty: float = 1.0
    recurrence: float = 1.0
    consequence: float = 1.0
    user_emphasis: float = 1.0
    recency: float = 1.0

    def __post_init__(self) -> None:
        has_positive_weight = False
        for item in fields(self):
            normalized = _validated_number(item.name, getattr(self, item.name), minimum=0.0)
            object.__setattr__(self, item.name, normalized)
            has_positive_weight = has_positive_weight or normalized > 0.0

        if not has_positive_weight:
            raise ValueError("salience config must contain at least one positive weight")


@dataclass(frozen=True, slots=True)
class SalienceAssessment:
    """Deterministic, inspectable salience result."""

    score: float
    reason_codes: tuple[SalienceReasonCode, ...]
    normalized_signals: tuple[tuple[str, float], ...]
    assessment_version: str


def _validated_number(
    name: str,
    value: float,
    *,
    minimum: float,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be a finite number")

    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    if normalized < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and normalized > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return normalized
