# SPDX-License-Identifier: MPL-2.0
"""Controlled M6 source benchmark. Not a real-corpus quality claim."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from cyberbrain.schemas.models import IdentityTrust
from cyberbrain.self_model import (
    SelfModelEvidenceDiversity,
    SelfModelEvidenceSample,
    SelfModelHypothesisEngine,
    SelfModelReadinessEvaluator,
    SelfModelReadinessInput,
)

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class SelfModelBenchmarkReport:
    expected_hypotheses: int
    generated_hypotheses: int
    correct_kind_scope: int
    precision: float
    missing_expected: tuple[str, ...]
    unexpected: tuple[str, ...]


def run() -> SelfModelBenchmarkReport:
    samples = _samples()
    evidence_ids = tuple(eid for sample in samples for eid in sample.evidence_ids)
    readiness = SelfModelReadinessEvaluator().evaluate(
        SelfModelReadinessInput(
            agent_id="agent-a",
            resolved_outcomes=len(samples),
            trusted_resolved_outcomes=len(samples),
            diversity=SelfModelEvidenceDiversity(
                distinct_sessions=len({sample.session_id for sample in samples}),
                distinct_projects=1,
                distinct_topics=len({sample.topic for sample in samples}),
            ),
            evidence_ids=evidence_ids,
        )
    )
    generated = SelfModelHypothesisEngine().generate(
        readiness=readiness,
        samples=samples,
        generated_at=NOW,
    )
    actual = {(item.kind.value, item.scope_topic) for item in generated}
    expected = {
        ("capability", "deploy"),
        ("limitation", "tests"),
        ("uncertain_capability", "research"),
        ("workflow_tendency", None),
        ("strategy_constraint", None),
    }
    correct = len(actual & expected)
    precision = correct / len(actual) if actual else 0.0
    return SelfModelBenchmarkReport(
        expected_hypotheses=len(expected),
        generated_hypotheses=len(actual),
        correct_kind_scope=correct,
        precision=precision,
        missing_expected=tuple(sorted(repr(item) for item in expected - actual)),
        unexpected=tuple(sorted(repr(item) for item in actual - expected)),
    )


def _samples() -> tuple[SelfModelEvidenceSample, ...]:
    rows: list[tuple[str, str, str, str | None]] = []
    rows.extend(("deploy", f"d{index % 4}", "confirmed", "check-first") for index in range(8))
    rows.extend(
        (
            "tests",
            f"t{index % 3}",
            "contradicted" if index < 4 else "partially_confirmed",
            "skip-validation",
        )
        for index in range(6)
    )
    rows.extend(
        (
            "research",
            f"r{index % 3}",
            "confirmed" if index < 4 else "contradicted",
            None,
        )
        for index in range(6)
    )
    result = []
    for index, (topic, session, assessment, strategy) in enumerate(rows):
        result.append(
            SelfModelEvidenceSample(
                prediction_id=str(uuid5(NAMESPACE_URL, f"m6-p-{index}")),
                outcome_id=str(uuid5(NAMESPACE_URL, f"m6-o-{index}")),
                agent_id="agent-a",
                session_id=session,
                project="CyberBrain",
                topic=topic,
                assessment=assessment,
                prediction_confidence=0.8,
                prediction_error=0.8 if assessment == "contradicted" else 0.0,
                identity_trust=IdentityTrust.AUTHENTICATED,
                strategy_tags=((strategy,) if strategy else ()),
            )
        )
    return tuple(result)
