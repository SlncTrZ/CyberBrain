# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean
from time import perf_counter

from .models import RankedHit, RetrievalIntent


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    case_id: str
    query: str
    intent: RetrievalIntent
    expected_ids: tuple[str, ...]
    acceptable_ids: tuple[str, ...] = ()
    forbidden_ids: tuple[str, ...] = ()
    project: str | None = None
    topic: str | None = None
    entity_name: str | None = None
    status: str | None = None
    not_after: datetime | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must not be empty")
        if not self.query.strip():
            raise ValueError("query must not be empty")
        if not self.expected_ids:
            raise ValueError("expected_ids must not be empty")


@dataclass(frozen=True, slots=True)
class CaseMetrics:
    case_id: str
    recall_at_k: float
    reciprocal_rank: float
    contamination_rate: float
    temporal_correct: bool
    returned_token_estimate: int
    latency_ms: float


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    cases: int
    mean_recall_at_k: float
    mean_reciprocal_rank: float
    contamination_rate: float
    temporal_correct_rate: float
    mean_returned_token_estimate: float
    mean_latency_ms: float
    by_intent: dict[str, dict[str, float]] = field(default_factory=dict)


class BenchmarkEvaluator:
    def __init__(self, *, k: int = 5, chars_per_token: int = 4) -> None:
        if k < 1:
            raise ValueError("k must be positive")
        if chars_per_token < 1:
            raise ValueError("chars_per_token must be positive")
        self._k = k
        self._chars_per_token = chars_per_token

    def evaluate_case(
        self,
        case: BenchmarkCase,
        ranked: list[RankedHit],
        *,
        text_by_id: dict[str, str] | None = None,
        event_time_by_id: dict[str, datetime] | None = None,
        latency_ms: float = 0.0,
    ) -> CaseMetrics:
        selected = ranked[: self._k]
        ids = [item.id for item in selected]
        relevant = set(case.expected_ids) | set(case.acceptable_ids)
        expected = set(case.expected_ids)
        hits = sum(1 for record_id in ids if record_id in expected)
        recall = hits / len(expected)

        reciprocal_rank = 0.0
        for rank, record_id in enumerate(ids, start=1):
            if record_id in relevant:
                reciprocal_rank = 1.0 / rank
                break

        forbidden = set(case.forbidden_ids)
        contamination = (
            (sum(1 for record_id in ids if record_id in forbidden) / len(ids)) if ids else 0.0
        )

        temporal_correct = True
        if case.not_after is not None and event_time_by_id is not None:
            for record_id in ids:
                event_time = event_time_by_id.get(record_id)
                if event_time is not None and event_time > case.not_after:
                    temporal_correct = False
                    break

        returned_tokens = 0
        if text_by_id:
            returned_chars = sum(len(text_by_id.get(record_id, "")) for record_id in ids)
            returned_tokens = (returned_chars + self._chars_per_token - 1) // self._chars_per_token

        return CaseMetrics(
            case_id=case.case_id,
            recall_at_k=round(recall, 6),
            reciprocal_rank=round(reciprocal_rank, 6),
            contamination_rate=round(contamination, 6),
            temporal_correct=temporal_correct,
            returned_token_estimate=returned_tokens,
            latency_ms=round(latency_ms, 6),
        )

    def run(
        self,
        cases: list[BenchmarkCase],
        runner,
    ) -> BenchmarkReport:
        metrics: list[tuple[BenchmarkCase, CaseMetrics]] = []
        for case in cases:
            started = perf_counter()
            ranked, texts, event_times = runner(case)
            elapsed = (perf_counter() - started) * 1000
            metrics.append(
                (
                    case,
                    self.evaluate_case(
                        case,
                        ranked,
                        text_by_id=texts,
                        event_time_by_id=event_times,
                        latency_ms=elapsed,
                    ),
                )
            )
        return self.aggregate(metrics)

    @staticmethod
    def aggregate(metrics: list[tuple[BenchmarkCase, CaseMetrics]]) -> BenchmarkReport:
        if not metrics:
            return BenchmarkReport(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {})

        grouped: dict[str, list[CaseMetrics]] = {}
        for case, item in metrics:
            grouped.setdefault(case.intent.value, []).append(item)

        def summary(items: list[CaseMetrics]) -> dict[str, float]:
            return {
                "cases": float(len(items)),
                "recall_at_k": round(mean(i.recall_at_k for i in items), 6),
                "mrr": round(mean(i.reciprocal_rank for i in items), 6),
                "contamination_rate": round(mean(i.contamination_rate for i in items), 6),
                "temporal_correct_rate": round(
                    mean(1.0 if i.temporal_correct else 0.0 for i in items), 6
                ),
            }

        items = [item for _case, item in metrics]
        return BenchmarkReport(
            cases=len(items),
            mean_recall_at_k=round(mean(i.recall_at_k for i in items), 6),
            mean_reciprocal_rank=round(mean(i.reciprocal_rank for i in items), 6),
            contamination_rate=round(mean(i.contamination_rate for i in items), 6),
            temporal_correct_rate=round(mean(1.0 if i.temporal_correct else 0.0 for i in items), 6),
            mean_returned_token_estimate=round(mean(i.returned_token_estimate for i in items), 3),
            mean_latency_ms=round(mean(i.latency_ms for i in items), 6),
            by_intent={key: summary(value) for key, value in sorted(grouped.items())},
        )
