# SPDX-License-Identifier: MPL-2.0
"""Read-only E2 census for prospective Prediction/Outcome evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class OutcomeEvidencePair:
    prediction_id: str
    prediction_record_id: str
    outcome_record_id: str
    agent: str
    session_id: str
    project: str | None
    topic: str | None
    assessment: str
    confidence: float
    prediction_time: str
    outcome_time: str


@dataclass(frozen=True, slots=True)
class AgentOutcomeEvidenceSummary:
    agent: str
    resolved_pairs: int
    distinct_sessions: int
    distinct_projects: int
    distinct_topics: int
    assessment_counts: dict[str, int]
    evidence_ids: tuple[str, ...]
    non_confirmed_outcome_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OutcomeReadinessCensus:
    total_rows: int
    predictions_seen: int
    outcomes_seen: int
    valid_pairs: int
    invalid_prediction_records: int
    invalid_outcome_records: int
    duplicate_outcomes: int
    missing_agent_pairs: int
    agent_summaries: tuple[AgentOutcomeEvidenceSummary, ...]
    historical_prediction_backfill_candidates: int = 0


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload")
    return dict(payload) if isinstance(payload, dict) else dict(row)


def _cognition(payload: dict[str, Any]) -> dict[str, Any] | None:
    context = payload.get("context")
    if not isinstance(context, dict):
        return None
    cognition = context.get("cognition")
    return cognition if isinstance(cognition, dict) else None


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _same_optional_identity(prediction: dict[str, Any], outcome: dict[str, Any], key: str) -> bool:
    return (prediction.get(key) or None) == (outcome.get(key) or None)


def census(
    rows: list[dict[str, Any]],
) -> tuple[OutcomeReadinessCensus, tuple[OutcomeEvidencePair, ...]]:
    predictions_seen = 0
    outcomes_seen = 0
    invalid_predictions = 0
    invalid_outcomes = 0
    missing_agent_pairs = 0

    predictions: dict[str, tuple[dict[str, Any], dict[str, Any], datetime]] = {}
    outcome_candidates: dict[
        str, list[tuple[dict[str, Any], dict[str, Any], datetime]]
    ] = {}

    for raw in rows:
        payload = _payload(raw)
        source = str(payload.get("source") or "")
        cognition = _cognition(payload)
        if source == "cognitive_prediction":
            predictions_seen += 1
            record_id = str(payload.get("id") or "").strip()
            event_time = _parse_time(payload.get("event_time"))
            confidence = cognition.get("confidence") if cognition else None
            expected = str(cognition.get("expected_outcome") or "").strip() if cognition else ""
            valid = (
                cognition is not None
                and cognition.get("kind") == "prediction"
                and record_id
                and str(cognition.get("prediction_id") or "") == record_id
                and event_time is not None
                and expected
                and isinstance(confidence, int | float)
                and not isinstance(confidence, bool)
                and 0 <= float(confidence) <= 1
            )
            if not valid:
                invalid_predictions += 1
                continue
            predictions[record_id] = (payload, cognition, event_time)
        elif source == "cognitive_outcome":
            outcomes_seen += 1
            event_time = _parse_time(payload.get("event_time"))
            prediction_id = str(cognition.get("prediction_id") or "") if cognition else ""
            valid = (
                cognition is not None
                and cognition.get("kind") == "outcome"
                and str(payload.get("id") or "").strip()
                and prediction_id
                and event_time is not None
                and str(cognition.get("assessment") or "")
            )
            if not valid:
                invalid_outcomes += 1
                continue
            outcome_candidates.setdefault(prediction_id, []).append(
                (payload, cognition, event_time)
            )

    pairs: list[OutcomeEvidencePair] = []
    duplicate_outcomes = 0
    for prediction_id, candidates in sorted(outcome_candidates.items()):
        prediction_row = predictions.get(prediction_id)
        if prediction_row is None:
            invalid_outcomes += len(candidates)
            continue
        prediction, prediction_cognition, prediction_time = prediction_row
        valid_candidates: list[tuple[dict[str, Any], dict[str, Any], datetime]] = []
        for outcome, outcome_cognition, outcome_time in candidates:
            identity_matches = (
                _same_optional_identity(prediction, outcome, "session_id")
                and _same_optional_identity(prediction, outcome, "agent")
                and _same_optional_identity(prediction, outcome, "project")
                and _same_optional_identity(prediction, outcome, "topic")
            )
            expected_matches = str(outcome_cognition.get("expected_outcome") or "") == str(
                prediction_cognition.get("expected_outcome") or ""
            )
            confidence_matches = outcome_cognition.get("prediction_confidence") == (
                prediction_cognition.get("confidence")
            )
            if (
                outcome_time < prediction_time
                or not identity_matches
                or not expected_matches
                or not confidence_matches
            ):
                invalid_outcomes += 1
                continue
            valid_candidates.append((outcome, outcome_cognition, outcome_time))

        if not valid_candidates:
            continue
        valid_candidates.sort(key=lambda item: (item[2], str(item[0].get("id") or "")))
        duplicate_outcomes += max(0, len(valid_candidates) - 1)
        outcome, outcome_cognition, outcome_time = valid_candidates[-1]
        agent = str(prediction.get("agent") or "").strip()
        if not agent:
            missing_agent_pairs += 1
            continue
        pairs.append(
            OutcomeEvidencePair(
                prediction_id=prediction_id,
                prediction_record_id=str(prediction.get("id")),
                outcome_record_id=str(outcome.get("id")),
                agent=agent,
                session_id=str(prediction.get("session_id") or ""),
                project=(str(prediction.get("project")) if prediction.get("project") else None),
                topic=(str(prediction.get("topic")) if prediction.get("topic") else None),
                assessment=str(outcome_cognition.get("assessment")),
                confidence=float(prediction_cognition["confidence"]),
                prediction_time=prediction_time.isoformat(),
                outcome_time=outcome_time.isoformat(),
            )
        )

    summaries: list[AgentOutcomeEvidenceSummary] = []
    for agent in sorted({pair.agent for pair in pairs}):
        agent_pairs = [pair for pair in pairs if pair.agent == agent]
        assessments = Counter(pair.assessment for pair in agent_pairs)
        evidence_ids = tuple(
            evidence_id
            for pair in agent_pairs
            for evidence_id in (pair.prediction_record_id, pair.outcome_record_id)
        )
        non_confirmed_outcome_ids = tuple(
            pair.outcome_record_id
            for pair in agent_pairs
            if pair.assessment in {"contradicted", "partially_confirmed"}
        )
        summaries.append(
            AgentOutcomeEvidenceSummary(
                agent=agent,
                resolved_pairs=len(agent_pairs),
                distinct_sessions=len({pair.session_id for pair in agent_pairs}),
                distinct_projects=len({pair.project for pair in agent_pairs if pair.project}),
                distinct_topics=len({pair.topic for pair in agent_pairs if pair.topic}),
                assessment_counts=dict(sorted(assessments.items())),
                evidence_ids=evidence_ids,
                non_confirmed_outcome_ids=non_confirmed_outcome_ids,
            )
        )

    report = OutcomeReadinessCensus(
        total_rows=len(rows),
        predictions_seen=predictions_seen,
        outcomes_seen=outcomes_seen,
        valid_pairs=len(pairs),
        invalid_prediction_records=invalid_predictions,
        invalid_outcome_records=invalid_outcomes,
        duplicate_outcomes=duplicate_outcomes,
        missing_agent_pairs=missing_agent_pairs,
        agent_summaries=tuple(summaries),
        historical_prediction_backfill_candidates=0,
    )
    return report, tuple(pairs)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"JSONL row {line_number} must be an object")
        rows.append(value)
    return rows


def run(path: Path, *, include_pairs: bool = False) -> dict[str, Any]:
    report, pairs = census(_load_jsonl(path))
    output: dict[str, Any] = {
        "source": str(path),
        "report": asdict(report),
        "rule": (
            "E2 accepts only canonical prospective cognitive_prediction/cognitive_outcome records; "
            "historical prose is never reconstructed into prediction evidence"
        ),
    }
    if include_pairs:
        output["pairs"] = [asdict(pair) for pair in pairs]
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="CyberBrain E2 outcome-evidence readiness census")
    parser.add_argument("path", type=Path)
    parser.add_argument("--include-pairs", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.path, include_pairs=args.include_pairs), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
