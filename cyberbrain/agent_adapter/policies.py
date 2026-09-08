# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from collections.abc import Iterable

from cyberbrain.agent_adapter.models import (
    Consequence,
    DreamSignals,
    Observation,
    OutcomeMatch,
    PolicyDecision,
    PredictionDecision,
    PredictionIntent,
    SessionCloseout,
    TurnRecallIntent,
)


class LifecyclePolicy:
    """Deterministic lifecycle routing; no model reasoning or transport behavior."""

    def recall_operations(self, intent: TurnRecallIntent) -> tuple[str, ...]:
        operations: list[str] = []
        if intent.need_knowledge:
            operations.append("knowledge_search")
        if intent.need_history:
            operations.append("memory_search")
        if intent.need_timeline:
            operations.append("knowledge_timeline")
        return tuple(operations)


class PredictionPolicy:
    def decide(self, intent: PredictionIntent) -> PredictionDecision:
        if not intent.expected_outcome.strip():
            return PredictionDecision(False, "missing_expected_outcome")
        if not 0.0 <= intent.confidence <= 1.0:
            return PredictionDecision(False, "invalid_confidence")
        if intent.outcome_known:
            return PredictionDecision(False, "outcome_already_known")
        if not intent.observable_later:
            return PredictionDecision(False, "outcome_not_observable")
        if not intent.resolvable_with_evidence:
            return PredictionDecision(False, "not_evidence_resolvable")
        if intent.consequence in {Consequence.TRIVIAL, Consequence.LOW}:
            return PredictionDecision(False, "insufficient_consequence")
        return PredictionDecision(True, "meaningful_uncertain_outcome")


class OutcomeMatchPolicy:
    def match(self, pending: Iterable[dict], observation: Observation) -> OutcomeMatch:
        rows = list(pending)
        if observation.prediction_id:
            for row in rows:
                row_id = str(row.get("id") or row.get("prediction_id") or "")
                if row_id == observation.prediction_id:
                    return OutcomeMatch(observation.prediction_id, "prediction_id_match")
            return OutcomeMatch(None, "prediction_id_not_pending")

        if observation.correlation_id:
            matches: list[str] = []
            for row in rows:
                context = row.get("context") or {}
                extensions = row.get("extensions") or {}
                row_correlation = (
                    row.get("correlation_id")
                    or context.get("correlation_id")
                    or extensions.get("correlation_id")
                )
                if row_correlation == observation.correlation_id:
                    row_id = str(row.get("id") or row.get("prediction_id") or "").strip()
                    if row_id:
                        matches.append(row_id)
            if len(matches) == 1:
                return OutcomeMatch(matches[0], "correlation_id_match")
            if len(matches) > 1:
                return OutcomeMatch(None, "ambiguous_correlation_id")

        return OutcomeMatch(None, "no_deterministic_match")


class CloseoutPolicy:
    def __init__(self, *, max_chars: int = 1_200) -> None:
        if max_chars <= 0:
            raise ValueError("max_chars must be positive")
        self.max_chars = max_chars

    def render(self, closeout: SessionCloseout) -> str:
        sections = [("Goal", (closeout.goal,))]
        sections.extend(
            [
                ("Actions", closeout.actions),
                ("Decisions", closeout.decisions),
                ("Outcomes", closeout.outcomes),
                ("Unresolved", closeout.unresolved),
                ("Identifiers", closeout.identifiers),
            ]
        )

        chunks: list[str] = []
        for title, values in sections:
            cleaned = [value.strip() for value in values if value and value.strip()]
            if not cleaned:
                continue
            chunks.append(f"{title}: " + " | ".join(cleaned))

        text = "\n".join(chunks)
        if not text:
            raise ValueError("closeout must contain at least one non-empty field")
        if len(text) <= self.max_chars:
            return text
        if self.max_chars == 1:
            return text[:1]
        return text[: self.max_chars - 1].rstrip() + "…"


class DreamEnqueuePolicy:
    def decide(self, signals: DreamSignals) -> PolicyDecision:
        if signals.trivial_only:
            return PolicyDecision(False, ("trivial_session",))

        reasons: list[str] = []
        if signals.reusable_lesson:
            reasons.append("reusable_lesson")
        if signals.prediction_error:
            reasons.append("prediction_error")
        if signals.repeated_failure:
            reasons.append("repeated_failure")
        if signals.significant_change:
            reasons.append("significant_change")
        if signals.surprising_result:
            reasons.append("surprising_result")

        if not reasons:
            return PolicyDecision(False, ("no_material_consolidation_signal",))
        return PolicyDecision(True, tuple(reasons))
