# SPDX-License-Identifier: MPL-2.0
"""Benchmark adapter for CyberBrain's reviewed Salience policy."""

from __future__ import annotations

import json
from dataclasses import asdict

from cyberbrain.salience import SalienceAdvisor, SalienceCandidate, SalienceInput

from .benchmark import EvaluationReport, Prediction, SalienceCase, evaluate_predictions, load_cases


def reviewed_policy_prediction(case: SalienceCase) -> Prediction:
    if case.candidate_a.scope_marker != case.candidate_b.scope_marker:
        return "not_comparable"

    advisory = SalienceAdvisor().assess(
        [
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
    )
    first, second = advisory.priority_order
    score_by_id = {
        item.candidate_id: item.assessment.score for item in advisory.assessments
    }
    first_score = score_by_id[first]
    second_score = score_by_id[second]
    if first_score == second_score:
        return "tie"
    return "a_higher" if first == case.candidate_a.candidate_id else "b_higher"


def evaluate_reviewed_policy() -> EvaluationReport:
    return evaluate_predictions(load_cases(), reviewed_policy_prediction)


def run() -> dict[str, object]:
    report = evaluate_reviewed_policy()
    return {
        "policy": "salience-policy-v1",
        "report": asdict(report),
        "note": (
            "Synthetic reviewed fixture evidence validates bounded policy semantics only; "
            "it is not production outcome evidence."
        ),
    }


def main() -> None:
    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
