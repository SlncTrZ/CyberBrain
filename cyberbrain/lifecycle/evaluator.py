# SPDX-License-Identifier: MPL-2.0
"""Deterministic M7 lifecycle scoring and reversible decisions."""

from __future__ import annotations

import math

from cyberbrain.schemas.models import LifecycleState, RetentionDirective

from .models import (
    LifecycleDecision,
    LifecycleDecisionKind,
    LifecyclePolicy,
    LifecycleReasonCode,
    LifecycleSignals,
)


class LifecycleEvaluator:
    def __init__(self, policy: LifecyclePolicy | None = None) -> None:
        self._policy = policy or LifecyclePolicy()

    def evaluate(self, signals: LifecycleSignals) -> LifecycleDecision:
        reasons: list[LifecycleReasonCode] = []
        if signals.retention_directive is RetentionDirective.KEEP:
            reasons.append(LifecycleReasonCode.EXPLICIT_KEEP)
            return LifecycleDecision(
                record_id=signals.record_id,
                decision=(
                    LifecycleDecisionKind.REACTIVATE
                    if signals.lifecycle_state is LifecycleState.SUPPRESSED
                    else LifecycleDecisionKind.KEEP_ACTIVE
                ),
                retention_score=1.0,
                reason_codes=tuple(reasons),
            )

        score = self._score(signals, reasons)

        if signals.lifecycle_state is LifecycleState.SUPPRESSED:
            if (
                signals.explicit_relevance
                or signals.unresolved
                or signals.salience_score >= self._policy.reactivation_threshold
                or score >= self._policy.reactivation_threshold
            ):
                if signals.explicit_relevance:
                    reasons.append(LifecycleReasonCode.EXPLICIT_RELEVANCE)
                reasons.append(LifecycleReasonCode.ABOVE_REACTIVATION_THRESHOLD)
                return LifecycleDecision(
                    record_id=signals.record_id,
                    decision=LifecycleDecisionKind.REACTIVATE,
                    retention_score=score,
                    reason_codes=tuple(dict.fromkeys(reasons)),
                )
            return LifecycleDecision(
                record_id=signals.record_id,
                decision=LifecycleDecisionKind.REMAIN_SUPPRESSED,
                retention_score=score,
                reason_codes=tuple(dict.fromkeys(reasons)),
            )

        protected = signals.explicit_relevance or signals.unresolved
        if protected:
            if signals.explicit_relevance:
                reasons.append(LifecycleReasonCode.EXPLICIT_RELEVANCE)
            if signals.unresolved:
                reasons.append(LifecycleReasonCode.UNRESOLVED)
            return LifecycleDecision(
                record_id=signals.record_id,
                decision=LifecycleDecisionKind.KEEP_ACTIVE,
                retention_score=max(score, self._policy.suppression_threshold),
                reason_codes=tuple(dict.fromkeys(reasons)),
            )

        if score < self._policy.suppression_threshold:
            reasons.append(LifecycleReasonCode.BELOW_SUPPRESSION_THRESHOLD)
            return LifecycleDecision(
                record_id=signals.record_id,
                decision=LifecycleDecisionKind.SUPPRESS,
                retention_score=score,
                reason_codes=tuple(dict.fromkeys(reasons)),
            )
        return LifecycleDecision(
            record_id=signals.record_id,
            decision=LifecycleDecisionKind.KEEP_ACTIVE,
            retention_score=score,
            reason_codes=tuple(dict.fromkeys(reasons)),
        )

    def _score(
        self,
        signals: LifecycleSignals,
        reasons: list[LifecycleReasonCode],
    ) -> float:
        recency = max(0.0, 1.0 - signals.age_days / self._policy.stale_days)
        if signals.age_days <= self._policy.recent_days:
            reasons.append(LifecycleReasonCode.RECENT)

        if signals.days_since_last_access is None:
            last_access = 0.0
            reasons.append(LifecycleReasonCode.NEVER_ACCESSED)
        else:
            last_access = max(
                0.0,
                1.0 - signals.days_since_last_access / self._policy.stale_days,
            )

        access = min(
            1.0,
            math.log1p(signals.access_count) / math.log1p(self._policy.frequent_access_count),
        )
        if signals.access_count >= self._policy.frequent_access_count:
            reasons.append(LifecycleReasonCode.FREQUENTLY_ACCESSED)
        if signals.salience_score >= 0.7:
            reasons.append(LifecycleReasonCode.HIGH_SALIENCE)
        if signals.concept_linked:
            reasons.append(LifecycleReasonCode.CONCEPT_LINKED)
        if signals.unresolved:
            reasons.append(LifecycleReasonCode.UNRESOLVED)
        if signals.age_days >= self._policy.stale_days:
            reasons.append(LifecycleReasonCode.STALE)
        if signals.superseded_or_contradicted:
            reasons.append(LifecycleReasonCode.SUPERSEDED_OR_CONTRADICTED)
        if signals.storage_pressure >= 0.5:
            reasons.append(LifecycleReasonCode.STORAGE_PRESSURE)

        raw = (
            0.10
            + 0.18 * recency
            + 0.12 * last_access
            + 0.15 * access
            + 0.22 * signals.salience_score
            + (0.10 if signals.concept_linked else 0.0)
            + (0.15 if signals.unresolved else 0.0)
            - (0.20 if signals.superseded_or_contradicted else 0.0)
            - 0.12 * signals.storage_pressure
        )
        return min(1.0, max(0.0, raw))
