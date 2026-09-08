# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

Disposition = Literal["lexical_better", "vector_better", "tie", "unknown"]
EvidenceSource = Literal[
    "fixture_only", "sanitized_reviewed_observation", "owner_reviewed_observation"
]

_ALLOWED_DISPOSITIONS = frozenset({"lexical_better", "vector_better", "tie", "unknown"})
_ALLOWED_SOURCES = frozenset(
    {"fixture_only", "sanitized_reviewed_observation", "owner_reviewed_observation"}
)
_DEFAULT_FIXTURE = Path(__file__).with_name("review_cases.json")


@dataclass(frozen=True, slots=True)
class RetrievalReviewCase:
    case_id: str
    query_fingerprint: str
    scope_marker: str
    vector_top_ids: tuple[str, ...]
    lexical_top_ids: tuple[str, ...]
    reviewed_relevant_ids: tuple[str, ...]
    known_vector_miss: bool
    scope_leakage: bool
    shadow_failure: bool
    disposition: Disposition
    token_delta: float | None = None
    latency_delta_ms: float | None = None
    scoring_observation: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievalReviewDataset:
    evidence_source: EvidenceSource
    cases: tuple[RetrievalReviewCase, ...]


@dataclass(frozen=True, slots=True)
class RetrievalClosureSummary:
    sample_count: int
    reviewed_sample_count: int
    lexical_wins: int
    vector_wins: int
    ties: int
    unknown: int
    top1_changed_count: int
    top1_changed_reviewed_count: int
    top1_change_improved_count: int
    top1_change_regressed_count: int
    top1_change_neutral_count: int
    scope_leakage_count: int
    failure_count: int
    known_vector_miss_count: int
    known_miss_rescue_count: int
    token_delta_samples: int
    mean_token_delta: float | None
    latency_delta_samples: int
    mean_latency_delta_ms: float | None


def _require_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _id_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    result = tuple(_require_text(item, field=f"{field}[]") for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"{field} must not contain duplicate IDs")
    return result


def _optional_number(value: Any, *, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric or null")
    return float(value)


def load_review_dataset(path: Path = _DEFAULT_FIXTURE) -> RetrievalReviewDataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("retrieval review fixture must be a schema_version=1 object")

    source = raw.get("evidence_source")
    if source not in _ALLOWED_SOURCES:
        raise ValueError(f"invalid evidence_source: {source!r}")
    rows = raw.get("cases")
    if not isinstance(rows, list):
        raise ValueError("retrieval review fixture must contain a cases list")

    seen: set[str] = set()
    cases: list[RetrievalReviewCase] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"cases[{index}] must be an object")
        if "query" in row:
            raise ValueError("raw query content is not allowed; use query_fingerprint")

        case_id = _require_text(row.get("case_id"), field=f"cases[{index}].case_id")
        if case_id in seen:
            raise ValueError(f"duplicate case_id: {case_id}")
        seen.add(case_id)

        disposition = row.get("disposition")
        if disposition not in _ALLOWED_DISPOSITIONS:
            raise ValueError(f"{case_id}.disposition is invalid: {disposition!r}")
        relevant = _id_tuple(
            row.get("reviewed_relevant_ids"),
            field=f"{case_id}.reviewed_relevant_ids",
        )
        if disposition != "unknown" and not relevant:
            raise ValueError(f"{case_id} needs reviewed_relevant_ids for a reviewed disposition")

        boolean_fields: dict[str, bool] = {}
        for field in ("known_vector_miss", "scope_leakage", "shadow_failure"):
            value = row.get(field)
            if not isinstance(value, bool):
                raise ValueError(f"{case_id}.{field} must be boolean")
            boolean_fields[field] = value

        observation = row.get("scoring_observation")
        if observation is not None:
            observation = _require_text(observation, field=f"{case_id}.scoring_observation")

        cases.append(
            RetrievalReviewCase(
                case_id=case_id,
                query_fingerprint=_require_text(
                    row.get("query_fingerprint"), field=f"{case_id}.query_fingerprint"
                ),
                scope_marker=_require_text(
                    row.get("scope_marker"), field=f"{case_id}.scope_marker"
                ),
                vector_top_ids=_id_tuple(
                    row.get("vector_top_ids"), field=f"{case_id}.vector_top_ids"
                ),
                lexical_top_ids=_id_tuple(
                    row.get("lexical_top_ids"), field=f"{case_id}.lexical_top_ids"
                ),
                reviewed_relevant_ids=relevant,
                known_vector_miss=boolean_fields["known_vector_miss"],
                scope_leakage=boolean_fields["scope_leakage"],
                shadow_failure=boolean_fields["shadow_failure"],
                disposition=disposition,
                token_delta=_optional_number(
                    row.get("token_delta"), field=f"{case_id}.token_delta"
                ),
                latency_delta_ms=_optional_number(
                    row.get("latency_delta_ms"), field=f"{case_id}.latency_delta_ms"
                ),
                scoring_observation=observation,
            )
        )

    return RetrievalReviewDataset(evidence_source=source, cases=tuple(cases))


def _top1(ids: tuple[str, ...]) -> str | None:
    return ids[0] if ids else None


def _has_relevant(ids: tuple[str, ...], relevant: set[str]) -> bool:
    return any(record_id in relevant for record_id in ids)


def summarize(dataset: RetrievalReviewDataset) -> RetrievalClosureSummary:
    lexical_wins = 0
    vector_wins = 0
    ties = 0
    unknown = 0
    top1_changed = 0
    top1_reviewed = 0
    top1_improved = 0
    top1_regressed = 0
    top1_neutral = 0
    leakage = 0
    failures = 0
    known_misses = 0
    rescues = 0
    token_deltas: list[float] = []
    latency_deltas: list[float] = []

    for case in dataset.cases:
        if case.disposition == "lexical_better":
            lexical_wins += 1
        elif case.disposition == "vector_better":
            vector_wins += 1
        elif case.disposition == "tie":
            ties += 1
        else:
            unknown += 1

        if case.scope_leakage:
            leakage += 1
        if case.shadow_failure:
            failures += 1
        if case.known_vector_miss:
            known_misses += 1

        relevant = set(case.reviewed_relevant_ids)
        vector_has_relevant = _has_relevant(case.vector_top_ids, relevant)
        lexical_has_relevant = _has_relevant(case.lexical_top_ids, relevant)
        if case.known_vector_miss and not vector_has_relevant and lexical_has_relevant:
            rescues += 1

        if _top1(case.vector_top_ids) != _top1(case.lexical_top_ids):
            top1_changed += 1
            if relevant:
                top1_reviewed += 1
                vector_top_relevant = _top1(case.vector_top_ids) in relevant
                lexical_top_relevant = _top1(case.lexical_top_ids) in relevant
                if lexical_top_relevant and not vector_top_relevant:
                    top1_improved += 1
                elif vector_top_relevant and not lexical_top_relevant:
                    top1_regressed += 1
                else:
                    top1_neutral += 1

        if case.token_delta is not None:
            token_deltas.append(case.token_delta)
        if case.latency_delta_ms is not None:
            latency_deltas.append(case.latency_delta_ms)

    reviewed = lexical_wins + vector_wins + ties
    return RetrievalClosureSummary(
        sample_count=len(dataset.cases),
        reviewed_sample_count=reviewed,
        lexical_wins=lexical_wins,
        vector_wins=vector_wins,
        ties=ties,
        unknown=unknown,
        top1_changed_count=top1_changed,
        top1_changed_reviewed_count=top1_reviewed,
        top1_change_improved_count=top1_improved,
        top1_change_regressed_count=top1_regressed,
        top1_change_neutral_count=top1_neutral,
        scope_leakage_count=leakage,
        failure_count=failures,
        known_vector_miss_count=known_misses,
        known_miss_rescue_count=rescues,
        token_delta_samples=len(token_deltas),
        mean_token_delta=(round(statistics.mean(token_deltas), 3) if token_deltas else None),
        latency_delta_samples=len(latency_deltas),
        mean_latency_delta_ms=(
            round(statistics.mean(latency_deltas), 3) if latency_deltas else None
        ),
    )


def closure_checklist(
    dataset: RetrievalReviewDataset,
    summary: RetrievalClosureSummary,
    *,
    min_reviewed: int = 5,
) -> dict[str, object]:
    if min_reviewed < 1:
        raise ValueError("min_reviewed must be positive")

    checks = {
        "owner_reviewed_source": dataset.evidence_source == "owner_reviewed_observation",
        "minimum_reviewed_samples": summary.reviewed_sample_count >= min_reviewed,
        "all_samples_reviewed": summary.unknown == 0,
        "scope_leakage_zero": summary.scope_leakage_count == 0,
        "shadow_failures_zero": summary.failure_count == 0,
        "lexical_losses_zero": summary.vector_wins == 0,
        "top1_regressions_zero": summary.top1_change_regressed_count == 0,
        "bounded_benefit_observed": (
            summary.lexical_wins > 0
            or summary.known_miss_rescue_count > 0
            or summary.top1_change_improved_count > 0
        ),
    }

    evidence_complete = (
        checks["owner_reviewed_source"]
        and checks["minimum_reviewed_samples"]
        and checks["all_samples_reviewed"]
    )
    unsafe = not (
        checks["scope_leakage_zero"]
        and checks["shadow_failures_zero"]
        and checks["lexical_losses_zero"]
        and checks["top1_regressions_zero"]
    )

    if not evidence_complete:
        decision_state = "insufficient_evidence"
    elif unsafe or not checks["bounded_benefit_observed"]:
        decision_state = "retain_vector_only"
    else:
        decision_state = "candidate_for_owner_promotion_review"

    return {
        "decision_state": decision_state,
        "changes_runtime_behavior": False,
        "checks": checks,
        "notes": (
            "This is an evidence gate only. candidate_for_owner_promotion_review never activates "
            "retrieval behavior or feature flags. Token/latency deltas remain review evidence, not "
            "automatic performance thresholds."
        ),
    }


def run(path: Path = _DEFAULT_FIXTURE, *, min_reviewed: int = 5) -> dict[str, object]:
    dataset = load_review_dataset(path)
    summary = summarize(dataset)
    return {
        "fixture": str(path),
        "evidence_source": dataset.evidence_source,
        "summary": asdict(summary),
        "closure": closure_checklist(dataset, summary, min_reviewed=min_reviewed),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize literal-shadow retrieval closure evidence"
    )
    parser.add_argument("--cases", type=Path, default=_DEFAULT_FIXTURE)
    parser.add_argument("--min-reviewed", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(run(args.cases, min_reviewed=args.min_reviewed), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
