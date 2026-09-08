# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

Prediction = Literal["a_higher", "b_higher", "tie", "ambiguous", "not_comparable"]
ScoredPrediction = Literal["a_higher", "b_higher", "tie"]

_ALLOWED_SIGNALS = frozenset(
    {
        "prediction_error",
        "unresolved",
        "contradiction",
        "user_emphasis",
        "consequence",
        "novelty",
        "recurrence",
        "recency",
    }
)
_ALLOWED_EXPECTED = frozenset(
    {"a_higher", "b_higher", "tie", "ambiguous", "not_comparable"}
)
_DEFAULT_FIXTURE = Path(__file__).with_name("cases.json")


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    scope_marker: str
    signals: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class SalienceCase:
    case_id: str
    family: str
    candidate_a: Candidate
    candidate_b: Candidate
    expected: Prediction
    rationale_category: str
    rationale: str

    @property
    def comparable(self) -> bool:
        return self.expected != "not_comparable"


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    total_cases: int
    scored_cases: int
    correct_cases: int
    pairwise_accuracy: float
    tie_cases: int
    tie_correct: int
    tie_accuracy: float
    ambiguous_cases: int
    not_comparable_cases: int
    boundary_safe_cases: int
    boundary_safe_rate: float


def _require_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _parse_candidate(raw: Any, *, field: str) -> Candidate:
    if not isinstance(raw, dict):
        raise ValueError(f"{field} must be an object")
    candidate_id = _require_text(raw.get("candidate_id"), field=f"{field}.candidate_id")
    scope_marker = _require_text(raw.get("scope_marker"), field=f"{field}.scope_marker")
    signals_raw = raw.get("signals")
    if not isinstance(signals_raw, dict):
        raise ValueError(f"{field}.signals must be an object")

    unknown = set(signals_raw) - _ALLOWED_SIGNALS
    if unknown:
        raise ValueError(f"{field}.signals has unknown signals: {sorted(unknown)}")

    signals: dict[str, float] = {}
    for name, value in signals_raw.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field}.signals.{name} must be numeric")
        number = float(value)
        if not 0.0 <= number <= 1.0:
            raise ValueError(f"{field}.signals.{name} must be within [0, 1]")
        signals[name] = number

    return Candidate(candidate_id=candidate_id, scope_marker=scope_marker, signals=signals)


def load_cases(path: Path = _DEFAULT_FIXTURE) -> list[SalienceCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("salience fixture must be a schema_version=1 object")
    rows = raw.get("cases")
    if not isinstance(rows, list):
        raise ValueError("salience fixture must contain a cases list")

    seen: set[str] = set()
    cases: list[SalienceCase] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"cases[{index}] must be an object")
        case_id = _require_text(row.get("case_id"), field=f"cases[{index}].case_id")
        if case_id in seen:
            raise ValueError(f"duplicate case_id: {case_id}")
        seen.add(case_id)

        candidate_a = _parse_candidate(row.get("candidate_a"), field=f"{case_id}.candidate_a")
        candidate_b = _parse_candidate(row.get("candidate_b"), field=f"{case_id}.candidate_b")
        expected = row.get("expected")
        if expected not in _ALLOWED_EXPECTED:
            raise ValueError(f"{case_id}.expected is invalid: {expected!r}")

        scopes_match = candidate_a.scope_marker == candidate_b.scope_marker
        if not scopes_match and expected != "not_comparable":
            raise ValueError(f"{case_id} crosses scope boundaries but is not marked not_comparable")
        if scopes_match and expected == "not_comparable":
            raise ValueError(f"{case_id} is same-scope but marked not_comparable")

        cases.append(
            SalienceCase(
                case_id=case_id,
                family=_require_text(row.get("family"), field=f"{case_id}.family"),
                candidate_a=candidate_a,
                candidate_b=candidate_b,
                expected=expected,
                rationale_category=_require_text(
                    row.get("rationale_category"), field=f"{case_id}.rationale_category"
                ),
                rationale=_require_text(row.get("rationale"), field=f"{case_id}.rationale"),
            )
        )
    return cases


def _signal(candidate: Candidate, name: str) -> float:
    return float(candidate.signals.get(name, 0.0))


def _compare_values(a_value: float, b_value: float) -> ScoredPrediction:
    if a_value > b_value:
        return "a_higher"
    if b_value > a_value:
        return "b_higher"
    return "tie"


def _bounded_scope(
    case: SalienceCase,
    predictor: Callable[[SalienceCase], ScoredPrediction],
) -> Prediction:
    if case.candidate_a.scope_marker != case.candidate_b.scope_marker:
        return "not_comparable"
    return predictor(case)


def stable_input_order(case: SalienceCase) -> Prediction:
    return _bounded_scope(case, lambda _case: "a_higher")


def recency_only(case: SalienceCase) -> Prediction:
    return _bounded_scope(
        case,
        lambda current: _compare_values(
            _signal(current.candidate_a, "recency"),
            _signal(current.candidate_b, "recency"),
        ),
    )


def user_emphasis_only(case: SalienceCase) -> Prediction:
    return _bounded_scope(
        case,
        lambda current: _compare_values(
            _signal(current.candidate_a, "user_emphasis"),
            _signal(current.candidate_b, "user_emphasis"),
        ),
    )


def consequence_only(case: SalienceCase) -> Prediction:
    return _bounded_scope(
        case,
        lambda current: _compare_values(
            _signal(current.candidate_a, "consequence"),
            _signal(current.candidate_b, "consequence"),
        ),
    )


BASELINES: dict[str, Callable[[SalienceCase], Prediction]] = {
    "stable_input_order": stable_input_order,
    "recency_only": recency_only,
    "user_emphasis_only": user_emphasis_only,
    "consequence_only": consequence_only,
}


def evaluate_predictions(
    cases: list[SalienceCase], predictor: Callable[[SalienceCase], Prediction]
) -> EvaluationReport:
    scored = 0
    correct = 0
    tie_cases = 0
    tie_correct = 0
    ambiguous = 0
    not_comparable = 0
    boundary_safe = 0

    for case in cases:
        predicted = predictor(case)
        if predicted not in _ALLOWED_EXPECTED:
            raise ValueError(f"predictor returned invalid label for {case.case_id}: {predicted!r}")

        if case.expected == "ambiguous":
            ambiguous += 1
            continue
        if case.expected == "not_comparable":
            not_comparable += 1
            if predicted == "not_comparable":
                boundary_safe += 1
            continue

        scored += 1
        if case.expected == "tie":
            tie_cases += 1
            if predicted == "tie":
                tie_correct += 1
        if predicted == case.expected:
            correct += 1

    return EvaluationReport(
        total_cases=len(cases),
        scored_cases=scored,
        correct_cases=correct,
        pairwise_accuracy=round(correct / scored, 6) if scored else 0.0,
        tie_cases=tie_cases,
        tie_correct=tie_correct,
        tie_accuracy=round(tie_correct / tie_cases, 6) if tie_cases else 0.0,
        ambiguous_cases=ambiguous,
        not_comparable_cases=not_comparable,
        boundary_safe_cases=boundary_safe,
        boundary_safe_rate=(round(boundary_safe / not_comparable, 6) if not_comparable else 1.0),
    )


def run(path: Path = _DEFAULT_FIXTURE) -> dict[str, object]:
    cases = load_cases(path)
    return {
        "fixture": str(path),
        "case_count": len(cases),
        "case_families": sorted({case.family for case in cases}),
        "reports": {
            name: asdict(evaluate_predictions(cases, predictor))
            for name, predictor in BASELINES.items()
        },
        "caution": (
            "Benchmark-only baselines are intentionally trivial. They do not represent "
            "CyberBrain runtime Salience behavior or a promotion decision."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate trivial Salience baselines")
    parser.add_argument("--cases", type=Path, default=_DEFAULT_FIXTURE)
    args = parser.parse_args()
    print(json.dumps(run(args.cases), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
