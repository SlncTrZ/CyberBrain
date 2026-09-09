# SPDX-License-Identifier: MPL-2.0
"""Deterministic M6 hypothesis generation over trusted prospective outcomes."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from .models import (
    SelfModelEvidenceDiversity,
    SelfModelEvidenceSample,
    SelfModelHypothesis,
    SelfModelHypothesisKind,
)
from .readiness import SelfModelReadinessReport


@dataclass(frozen=True, slots=True)
class SelfModelHypothesisPolicy:
    minimum_topic_samples: int = 5
    minimum_topic_sessions: int = 2
    minimum_strategy_samples: int = 5
    minimum_strategy_sessions: int = 2
    capability_rate: float = 0.8
    limitation_rate: float = 0.4

    def __post_init__(self) -> None:
        for name in (
            "minimum_topic_samples",
            "minimum_topic_sessions",
            "minimum_strategy_samples",
            "minimum_strategy_sessions",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"self-model {name} must be a positive integer")
        if not 0.5 < self.capability_rate <= 1:
            raise ValueError("self-model capability_rate must be within (0.5, 1]")
        if not 0 < self.limitation_rate <= 1:
            raise ValueError("self-model limitation_rate must be within (0, 1]")


class SelfModelHypothesisEngine:
    """Generate read-only hypotheses after the global M6 readiness gate passes."""

    def __init__(self, policy: SelfModelHypothesisPolicy | None = None) -> None:
        self._policy = policy or SelfModelHypothesisPolicy()

    def generate(
        self,
        *,
        readiness: SelfModelReadinessReport,
        samples: tuple[SelfModelEvidenceSample, ...],
        generated_at: datetime,
    ) -> tuple[SelfModelHypothesis, ...]:
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            raise ValueError("self-model generated_at must include a timezone")
        if not readiness.ready:
            return ()

        agent_id = readiness.agent_id
        trusted = tuple(
            sample for sample in samples if sample.trusted and sample.agent_id == agent_id
        )
        if len(trusted) != readiness.resolved_outcomes:
            return ()

        hypotheses: list[SelfModelHypothesis] = []
        by_topic: dict[str, list[SelfModelEvidenceSample]] = defaultdict(list)
        for sample in trusted:
            if sample.topic:
                by_topic[sample.topic].append(sample)

        for topic in sorted(by_topic):
            group = tuple(by_topic[topic])
            if len(group) < self._policy.minimum_topic_samples:
                continue
            if len({sample.session_id for sample in group}) < self._policy.minimum_topic_sessions:
                continue
            hypothesis = self._topic_hypothesis(
                agent_id=agent_id,
                topic=topic,
                samples=group,
                generated_at=generated_at,
            )
            if hypothesis is not None:
                hypotheses.append(hypothesis)

        by_strategy: dict[str, list[SelfModelEvidenceSample]] = defaultdict(list)
        for sample in trusted:
            for tag in sample.strategy_tags:
                by_strategy[tag].append(sample)
        for strategy in sorted(by_strategy):
            group = tuple(by_strategy[strategy])
            if len(group) < self._policy.minimum_strategy_samples:
                continue
            if (
                len({sample.session_id for sample in group})
                < self._policy.minimum_strategy_sessions
            ):
                continue
            hypothesis = self._strategy_hypothesis(
                agent_id=agent_id,
                strategy=strategy,
                samples=group,
                generated_at=generated_at,
            )
            if hypothesis is not None:
                hypotheses.append(hypothesis)

        hypotheses.sort(
            key=lambda item: (item.kind.value, item.scope_topic or "", item.hypothesis_id)
        )
        return tuple(hypotheses)

    def _topic_hypothesis(
        self,
        *,
        agent_id: str,
        topic: str,
        samples: tuple[SelfModelEvidenceSample, ...],
        generated_at: datetime,
    ) -> SelfModelHypothesis | None:
        confirmed, partial, contradicted, usable = self._assessment_counts(samples)
        if usable == 0:
            return None
        success_rate = (confirmed + 0.5 * partial) / usable
        negative_rate = (contradicted + 0.5 * partial) / usable
        if success_rate >= self._policy.capability_rate:
            kind = SelfModelHypothesisKind.CAPABILITY
            claim = f"The agent has repeatedly produced successful outcomes for topic '{topic}'."
            support = self._evidence_ids(
                sample
                for sample in samples
                if sample.assessment in {"confirmed", "partially_confirmed"}
            )
            counter = self._evidence_ids(
                sample for sample in samples if sample.assessment == "contradicted"
            )
            confidence = self._confidence(success_rate, usable)
            reasons = (
                "topic_recurrence",
                "high_confirmed_outcome_rate",
                "prospective_trusted_evidence",
            )
        elif negative_rate >= self._policy.limitation_rate:
            kind = SelfModelHypothesisKind.LIMITATION
            claim = f"The agent has a recurring outcome limitation for topic '{topic}'."
            support = self._evidence_ids(
                sample
                for sample in samples
                if sample.assessment in {"contradicted", "partially_confirmed"}
            )
            counter = self._evidence_ids(
                sample for sample in samples if sample.assessment == "confirmed"
            )
            confidence = self._confidence(negative_rate, usable)
            reasons = (
                "topic_recurrence",
                "repeated_negative_outcomes",
                "prospective_trusted_evidence",
            )
        else:
            kind = SelfModelHypothesisKind.UNCERTAIN_CAPABILITY
            claim = f"Evidence for the agent's capability on topic '{topic}' remains mixed."
            support = self._evidence_ids(samples)
            counter = ()
            confidence = 0.5
            reasons = ("topic_recurrence", "mixed_outcomes", "prospective_trusted_evidence")

        return SelfModelHypothesis(
            hypothesis_id=self._stable_id(agent_id, kind, f"topic:{topic}"),
            agent_id=agent_id,
            kind=kind,
            claim=claim,
            support_evidence_ids=support,
            counterexample_evidence_ids=counter,
            confidence=confidence,
            sample_count=len(samples),
            diversity=self._diversity(samples),
            generated_at=generated_at,
            reason_codes=reasons,
            scope_topic=topic,
        )

    def _strategy_hypothesis(
        self,
        *,
        agent_id: str,
        strategy: str,
        samples: tuple[SelfModelEvidenceSample, ...],
        generated_at: datetime,
    ) -> SelfModelHypothesis | None:
        confirmed, partial, contradicted, usable = self._assessment_counts(samples)
        if usable == 0:
            return None
        success_rate = (confirmed + 0.5 * partial) / usable
        negative_rate = (contradicted + 0.5 * partial) / usable
        if success_rate >= self._policy.capability_rate:
            kind = SelfModelHypothesisKind.WORKFLOW_TENDENCY
            claim = f"Strategy '{strategy}' is repeatedly associated with successful outcomes."
            support = self._evidence_ids(
                sample
                for sample in samples
                if sample.assessment in {"confirmed", "partially_confirmed"}
            )
            counter = self._evidence_ids(
                sample for sample in samples if sample.assessment == "contradicted"
            )
            confidence = self._confidence(success_rate, usable)
            reasons = (
                "strategy_recurrence",
                "high_confirmed_outcome_rate",
                "correlational_not_causal",
            )
        elif negative_rate >= self._policy.limitation_rate:
            kind = SelfModelHypothesisKind.STRATEGY_CONSTRAINT
            claim = (
                f"Strategy '{strategy}' is repeatedly associated with weak outcomes "
                "and should be treated cautiously."
            )
            support = self._evidence_ids(
                sample
                for sample in samples
                if sample.assessment in {"contradicted", "partially_confirmed"}
            )
            counter = self._evidence_ids(
                sample for sample in samples if sample.assessment == "confirmed"
            )
            confidence = self._confidence(negative_rate, usable)
            reasons = (
                "strategy_recurrence",
                "repeated_negative_outcomes",
                "correlational_not_causal",
            )
        else:
            return None

        return SelfModelHypothesis(
            hypothesis_id=self._stable_id(agent_id, kind, f"strategy:{strategy}"),
            agent_id=agent_id,
            kind=kind,
            claim=claim,
            support_evidence_ids=support,
            counterexample_evidence_ids=counter,
            confidence=confidence,
            sample_count=len(samples),
            diversity=self._diversity(samples),
            generated_at=generated_at,
            reason_codes=reasons,
            scope_topic=None,
        )

    @staticmethod
    def _assessment_counts(
        samples: tuple[SelfModelEvidenceSample, ...],
    ) -> tuple[int, int, int, int]:
        confirmed = sum(sample.assessment == "confirmed" for sample in samples)
        partial = sum(sample.assessment == "partially_confirmed" for sample in samples)
        contradicted = sum(sample.assessment == "contradicted" for sample in samples)
        return confirmed, partial, contradicted, confirmed + partial + contradicted

    @staticmethod
    def _evidence_ids(samples) -> tuple[str, ...]:  # noqa: ANN001
        return tuple(
            dict.fromkeys(evidence_id for sample in samples for evidence_id in sample.evidence_ids)
        )

    @staticmethod
    def _diversity(samples: tuple[SelfModelEvidenceSample, ...]) -> SelfModelEvidenceDiversity:
        return SelfModelEvidenceDiversity(
            distinct_sessions=len({sample.session_id for sample in samples}),
            distinct_projects=len({sample.project for sample in samples if sample.project}),
            distinct_topics=len({sample.topic for sample in samples if sample.topic}),
        )

    @staticmethod
    def _confidence(rate: float, sample_count: int) -> float:
        sample_factor = min(sample_count, 20) / 20
        return min(0.95, max(0.5, 0.5 + (rate - 0.5) * 0.8 + sample_factor * 0.1))

    @staticmethod
    def _stable_id(agent_id: str, kind: SelfModelHypothesisKind, scope: str) -> str:
        digest = hashlib.sha256(f"{agent_id}|{kind.value}|{scope}".encode()).hexdigest()[:24]
        return f"smh-{digest}"
