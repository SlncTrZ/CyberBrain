# SPDX-License-Identifier: MPL-2.0
"""Metrics-only Salience shadow observation over authorized candidate sets."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from cyberbrain.core.metrics import MetricsRegistry

from .advisor import SalienceAdvisor, SalienceCandidate


@dataclass(frozen=True, slots=True)
class SalienceShadowReport:
    candidate_count: int
    non_neutral_count: int
    reordered: bool
    top1_changed: bool
    mean_score: float
    priority_order: tuple[str, ...]


class SalienceShadowObserver:
    """Observe advisory ordering without changing caller-visible candidate order."""

    def __init__(
        self,
        *,
        advisor: SalienceAdvisor | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._advisor = advisor or SalienceAdvisor()
        self._metrics = metrics or MetricsRegistry()

    def observe(
        self,
        candidates: tuple[SalienceCandidate, ...] | list[SalienceCandidate],
    ) -> SalienceShadowReport:
        started = monotonic()
        original = tuple(candidate.candidate_id for candidate in candidates)
        advisory = self._advisor.assess(candidates)
        scores = tuple(item.assessment.score for item in advisory.assessments)
        non_neutral = sum(score > 0.0 for score in scores)
        reordered = advisory.priority_order != original
        top1_changed = bool(
            original
            and advisory.priority_order
            and original[0] != advisory.priority_order[0]
        )

        self._metrics.increment("salience_shadow_evaluated_total")
        self._metrics.increment("salience_shadow_candidates_total", len(original))
        self._metrics.increment("salience_shadow_non_neutral_total", non_neutral)
        if reordered:
            self._metrics.increment("salience_shadow_reordered_total")
        if top1_changed:
            self._metrics.increment("salience_shadow_top1_changed_total")
        for score in scores:
            self._metrics.observe("salience_shadow_score", score)
        self._metrics.observe("salience_shadow_seconds", monotonic() - started)

        return SalienceShadowReport(
            candidate_count=len(original),
            non_neutral_count=non_neutral,
            reordered=reordered,
            top1_changed=top1_changed,
            mean_score=(sum(scores) / len(scores) if scores else 0.0),
            priority_order=advisory.priority_order,
        )
