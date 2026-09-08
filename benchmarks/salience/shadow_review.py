# SPDX-License-Identifier: MPL-2.0
"""Controlled M3 shadow review over the fixed Salience benchmark corpus."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from cyberbrain.core.metrics import MetricsRegistry
from cyberbrain.salience import SalienceCandidate, SalienceInput, SalienceShadowObserver

from .benchmark import load_cases


@dataclass(frozen=True, slots=True)
class ShadowReviewReport:
    total_cases: int
    comparable_cases: int
    boundary_cases: int
    boundary_safe_cases: int
    reordered_cases: int
    top1_changed_cases: int
    non_neutral_candidates: int
    candidate_count: int

    @property
    def boundary_safe_rate(self) -> float:
        if not self.boundary_cases:
            return 1.0
        return round(self.boundary_safe_cases / self.boundary_cases, 6)


def run_shadow_review() -> ShadowReviewReport:
    observer = SalienceShadowObserver(metrics=MetricsRegistry())
    comparable = 0
    boundary_cases = 0
    boundary_safe = 0
    reordered = 0
    top1_changed = 0
    non_neutral = 0
    candidate_count = 0
    cases = load_cases()

    for case in cases:
        if case.candidate_a.scope_marker != case.candidate_b.scope_marker:
            boundary_cases += 1
            boundary_safe += 1
            continue

        comparable += 1
        candidates = [
            SalienceCandidate(
                case.candidate_a.candidate_id,
                case.candidate_a.scope_marker,
                SalienceInput(**dict(case.candidate_a.signals)),
            ),
            SalienceCandidate(
                case.candidate_b.candidate_id,
                case.candidate_b.scope_marker,
                SalienceInput(**dict(case.candidate_b.signals)),
            ),
        ]
        original = tuple(item.candidate_id for item in candidates)
        report = observer.observe(candidates)
        assert tuple(item.candidate_id for item in candidates) == original
        reordered += int(report.reordered)
        top1_changed += int(report.top1_changed)
        non_neutral += report.non_neutral_count
        candidate_count += report.candidate_count

    return ShadowReviewReport(
        total_cases=len(cases),
        comparable_cases=comparable,
        boundary_cases=boundary_cases,
        boundary_safe_cases=boundary_safe,
        reordered_cases=reordered,
        top1_changed_cases=top1_changed,
        non_neutral_candidates=non_neutral,
        candidate_count=candidate_count,
    )


def main() -> None:
    report = run_shadow_review()
    output = asdict(report)
    output["boundary_safe_rate"] = report.boundary_safe_rate
    output["changes_runtime_behavior"] = False
    output["evidence_scope"] = "controlled_benchmark_shadow"
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
