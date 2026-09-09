# SPDX-License-Identifier: MPL-2.0
"""Controlled M7 lifecycle benchmark. Real-corpus activation remains separately gated."""

from __future__ import annotations

from dataclasses import dataclass

from cyberbrain.lifecycle import LifecycleDecisionKind, LifecycleEvaluator, LifecycleSignals
from cyberbrain.schemas.models import LifecycleState, RetentionDirective


@dataclass(frozen=True, slots=True)
class LifecycleBenchmarkReport:
    cases: int
    correct: int
    accuracy: float
    false_suppression: int
    false_reactivation: int


def run() -> LifecycleBenchmarkReport:
    cases = _cases()
    evaluator = LifecycleEvaluator()
    correct = 0
    false_suppression = 0
    false_reactivation = 0
    for signals, expected in cases:
        actual = evaluator.evaluate(signals).decision
        correct += actual is expected
        if (
            actual is LifecycleDecisionKind.SUPPRESS
            and expected is not LifecycleDecisionKind.SUPPRESS
        ):
            false_suppression += 1
        if (
            actual is LifecycleDecisionKind.REACTIVATE
            and expected is not LifecycleDecisionKind.REACTIVATE
        ):
            false_reactivation += 1
    return LifecycleBenchmarkReport(
        cases=len(cases),
        correct=correct,
        accuracy=correct / len(cases),
        false_suppression=false_suppression,
        false_reactivation=false_reactivation,
    )


def _cases() -> tuple[tuple[LifecycleSignals, LifecycleDecisionKind], ...]:
    return (
        (
            LifecycleSignals(
                record_id="fresh",
                lifecycle_state=LifecycleState.ACTIVE,
                retention_directive=RetentionDirective.DEFAULT,
                age_days=3,
                access_count=3,
                days_since_last_access=1,
                salience_score=0.8,
            ),
            LifecycleDecisionKind.KEEP_ACTIVE,
        ),
        (
            LifecycleSignals(
                record_id="stale",
                lifecycle_state=LifecycleState.ACTIVE,
                retention_directive=RetentionDirective.DEFAULT,
                age_days=400,
                access_count=0,
                days_since_last_access=None,
                salience_score=0.0,
                superseded_or_contradicted=True,
                storage_pressure=0.8,
            ),
            LifecycleDecisionKind.SUPPRESS,
        ),
        (
            LifecycleSignals(
                record_id="keep",
                lifecycle_state=LifecycleState.ACTIVE,
                retention_directive=RetentionDirective.KEEP,
                age_days=600,
                access_count=0,
                days_since_last_access=None,
                salience_score=0.0,
            ),
            LifecycleDecisionKind.KEEP_ACTIVE,
        ),
        (
            LifecycleSignals(
                record_id="reactivate",
                lifecycle_state=LifecycleState.SUPPRESSED,
                retention_directive=RetentionDirective.DEFAULT,
                age_days=300,
                access_count=0,
                days_since_last_access=None,
                salience_score=0.1,
                explicit_relevance=True,
            ),
            LifecycleDecisionKind.REACTIVATE,
        ),
        (
            LifecycleSignals(
                record_id="remain-suppressed",
                lifecycle_state=LifecycleState.SUPPRESSED,
                retention_directive=RetentionDirective.DEFAULT,
                age_days=500,
                access_count=0,
                days_since_last_access=None,
                salience_score=0.0,
            ),
            LifecycleDecisionKind.REMAIN_SUPPRESSED,
        ),
        (
            LifecycleSignals(
                record_id="unresolved",
                lifecycle_state=LifecycleState.ACTIVE,
                retention_directive=RetentionDirective.DEFAULT,
                age_days=300,
                access_count=0,
                days_since_last_access=None,
                salience_score=0.0,
                unresolved=True,
            ),
            LifecycleDecisionKind.KEEP_ACTIVE,
        ),
    )
