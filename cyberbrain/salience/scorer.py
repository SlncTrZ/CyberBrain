# SPDX-License-Identifier: MPL-2.0
"""Pure deterministic salience scoring."""

from __future__ import annotations

from dataclasses import dataclass

from .models import SalienceAssessment, SalienceConfig, SalienceInput, SalienceReasonCode

SALIENCE_ASSESSMENT_VERSION = "salience-assessment-v1"

_SIGNAL_ORDER: tuple[tuple[str, SalienceReasonCode], ...] = (
    ("prediction_error", SalienceReasonCode.PREDICTION_ERROR),
    ("unresolvedness", SalienceReasonCode.UNRESOLVEDNESS),
    ("contradiction", SalienceReasonCode.CONTRADICTION),
    ("novelty", SalienceReasonCode.NOVELTY),
    ("recurrence", SalienceReasonCode.RECURRENCE),
    ("consequence", SalienceReasonCode.CONSEQUENCE),
    ("user_emphasis", SalienceReasonCode.USER_EMPHASIS),
    ("recency", SalienceReasonCode.RECENCY),
)


@dataclass(frozen=True, slots=True)
class SalienceScorer:
    """Audit-friendly weighted aggregation over explicit bounded signals."""

    config: SalienceConfig

    def assess(self, item: SalienceInput) -> SalienceAssessment:
        considered: list[tuple[str, float, float, SalienceReasonCode]] = []
        for signal_name, reason_code in _SIGNAL_ORDER:
            value = getattr(item, signal_name)
            weight = getattr(self.config, signal_name)
            if value is None or weight == 0.0:
                continue
            considered.append((signal_name, value, weight, reason_code))

        if not considered:
            return SalienceAssessment(
                score=0.0,
                reason_codes=(),
                normalized_signals=(),
                assessment_version=SALIENCE_ASSESSMENT_VERSION,
            )

        # Scale by the largest active weight before aggregation so finite but very
        # large weights cannot overflow while preserving their relative ratios.
        largest_weight = max(weight for _name, _value, weight, _reason in considered)
        scaled = [
            (name, value, weight / largest_weight, reason)
            for name, value, weight, reason in considered
        ]
        total_weight = sum(weight for _name, _value, weight, _reason in scaled)
        weighted_sum = sum(value * weight for _name, value, weight, _reason in scaled)
        score = min(1.0, max(0.0, weighted_sum / total_weight))

        return SalienceAssessment(
            score=score,
            reason_codes=tuple(
                reason for _name, value, _weight, reason in scaled if value > 0.0
            ),
            normalized_signals=tuple((name, value) for name, value, _weight, _reason in scaled),
            assessment_version=SALIENCE_ASSESSMENT_VERSION,
        )
