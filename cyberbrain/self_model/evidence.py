# SPDX-License-Identifier: MPL-2.0
"""Canonical Prediction/Outcome evidence extraction for M6."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cyberbrain.schemas.models import EpisodeRecord, IdentityTrust
from cyberbrain.tenancy import normalize_identifier

from .models import SelfModelEvidenceDiversity, SelfModelEvidenceSample

_ELIGIBLE_ASSESSMENTS = {"confirmed", "partially_confirmed", "contradicted"}


@dataclass(frozen=True, slots=True)
class SelfModelEvidenceSet:
    agent_id: str
    samples: tuple[SelfModelEvidenceSample, ...]
    resolved_pairs: int
    trusted_resolved_pairs: int
    diversity: SelfModelEvidenceDiversity
    evidence_ids: tuple[str, ...]
    duplicate_outcomes: int
    invalid_records: int
    may_be_incomplete: bool = False


def extract_self_model_evidence(
    rows: list[dict[str, Any]],
    *,
    agent_id: str,
    may_be_incomplete: bool = False,
) -> SelfModelEvidenceSet:
    """Extract causally valid, agent-scoped pairs without fabricating missing metadata."""

    normalized_agent = normalize_identifier(agent_id)
    predictions: dict[str, tuple[EpisodeRecord, dict[str, Any]]] = {}
    outcomes: dict[str, list[tuple[EpisodeRecord, dict[str, Any]]]] = {}
    invalid = 0

    for row in rows:
        payload = dict(row.get("payload") or row)
        try:
            record = EpisodeRecord.model_validate(payload)
        except Exception:
            invalid += 1
            continue
        cognition = record.context.get("cognition")
        if not isinstance(cognition, dict):
            continue
        kind = cognition.get("kind")
        prediction_id = str(cognition.get("prediction_id") or "").strip()
        if not prediction_id:
            invalid += 1
            continue
        if kind == "prediction" and record.source == "cognitive_prediction":
            if str(record.id) != prediction_id:
                invalid += 1
                continue
            predictions[prediction_id] = (record, cognition)
        elif kind == "outcome" and record.source == "cognitive_outcome":
            outcomes.setdefault(prediction_id, []).append((record, cognition))

    samples: list[SelfModelEvidenceSample] = []
    duplicate_outcomes = 0
    for prediction_id in sorted(predictions):
        prediction, prediction_cognition = predictions[prediction_id]
        if prediction.agent is None or normalize_identifier(prediction.agent) != normalized_agent:
            continue
        candidates = outcomes.get(prediction_id, [])
        valid: list[tuple[EpisodeRecord, dict[str, Any]]] = []
        for outcome, outcome_cognition in candidates:
            assessment = str(outcome_cognition.get("assessment") or "")
            if assessment not in _ELIGIBLE_ASSESSMENTS:
                continue
            if outcome.event_time < prediction.event_time:
                invalid += 1
                continue
            if not _identity_matches(prediction, outcome):
                invalid += 1
                continue
            if str(outcome_cognition.get("expected_outcome") or "") != str(
                prediction_cognition.get("expected_outcome") or ""
            ):
                invalid += 1
                continue
            confidence = prediction_cognition.get("confidence")
            if outcome_cognition.get("prediction_confidence") != confidence:
                invalid += 1
                continue
            valid.append((outcome, outcome_cognition))
        if not valid:
            continue
        valid.sort(key=lambda item: (item[0].event_time, str(item[0].id)))
        duplicate_outcomes += max(0, len(valid) - 1)
        outcome, outcome_cognition = valid[-1]
        strategy_tags = _strategy_tags(prediction_cognition)
        samples.append(
            SelfModelEvidenceSample(
                prediction_id=prediction_id,
                outcome_id=str(outcome.id),
                agent_id=normalized_agent,
                session_id=prediction.session_id,
                project=prediction.project,
                topic=prediction.topic,
                assessment=str(outcome_cognition["assessment"]),
                prediction_confidence=float(prediction_cognition["confidence"]),
                prediction_error=_optional_float(
                    outcome_cognition.get("confidence_weighted_error")
                ),
                identity_trust=_pair_identity_trust(prediction, outcome),
                strategy_tags=strategy_tags,
            )
        )

    samples.sort(key=lambda item: (item.session_id, item.topic or "", item.prediction_id))
    trusted = [sample for sample in samples if sample.trusted]
    evidence_ids = tuple(
        dict.fromkeys(evidence_id for sample in samples for evidence_id in sample.evidence_ids)
    )
    return SelfModelEvidenceSet(
        agent_id=normalized_agent,
        samples=tuple(samples),
        resolved_pairs=len(samples),
        trusted_resolved_pairs=len(trusted),
        diversity=SelfModelEvidenceDiversity(
            distinct_sessions=len({sample.session_id for sample in trusted}),
            distinct_projects=len({sample.project for sample in trusted if sample.project}),
            distinct_topics=len({sample.topic for sample in trusted if sample.topic}),
        ),
        evidence_ids=evidence_ids,
        duplicate_outcomes=duplicate_outcomes,
        invalid_records=invalid,
        may_be_incomplete=may_be_incomplete,
    )


def _identity_matches(prediction: EpisodeRecord, outcome: EpisodeRecord) -> bool:
    return (
        prediction.session_id == outcome.session_id
        and prediction.agent == outcome.agent
        and prediction.project == outcome.project
        and prediction.topic == outcome.topic
    )


def _pair_identity_trust(prediction: EpisodeRecord, outcome: EpisodeRecord) -> IdentityTrust:
    if (
        prediction.identity_trust is IdentityTrust.AUTHENTICATED
        and outcome.identity_trust is IdentityTrust.AUTHENTICATED
    ):
        return IdentityTrust.AUTHENTICATED
    if (
        prediction.identity_trust is IdentityTrust.LEGACY_UNTRUSTED
        or outcome.identity_trust is IdentityTrust.LEGACY_UNTRUSTED
    ):
        return IdentityTrust.LEGACY_UNTRUSTED
    return IdentityTrust.UNSPECIFIED


def _strategy_tags(cognition: dict[str, Any]) -> tuple[str, ...]:
    raw = cognition.get("strategy_tags")
    if not isinstance(raw, list | tuple):
        return ()
    return tuple(sorted({str(value).strip() for value in raw if str(value).strip()}))


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
