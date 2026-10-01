# SPDX-License-Identifier: MPL-2.0
"""Controlled known-seed comparison; this is not a learned-embedding quality claim."""

from __future__ import annotations

import json
from dataclasses import dataclass
from statistics import mean
from time import perf_counter
from typing import Any

from cyberbrain.core.token_budget import DeterministicTokenCounter
from cyberbrain.knowledge.search import KnowledgeSearchService
from cyberbrain.retrieval.benchmark import BenchmarkCase, BenchmarkEvaluator
from cyberbrain.retrieval.models import RankedHit
from cyberbrain.retrieval.runtime import KnowledgeRetrievalPolicy
from cyberbrain.tenancy import current_authority

from .recall import RelationRecallRequest, RelationRecallService


@dataclass(frozen=True)
class RelationBenchmarkCase:
    baseline: BenchmarkCase
    request: RelationRecallRequest
    expected_paths: frozenset[tuple[str, ...]]


def percentile(values: list[float], percentile_value: float) -> float:
    if not values or not 0 <= percentile_value <= 1:
        raise ValueError("invalid percentile sample")
    ordered = sorted(values)
    # Linear interpolation makes the convention explicit and works with one sample.
    position = (len(ordered) - 1) * percentile_value
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


class RelationBenchmark:
    def __init__(
        self,
        *,
        repository,
        embedding,
        collection: str,
        service: RelationRecallService,
        iterations: int = 10,
        k: int = 8,
    ):
        if not 2 <= iterations <= 100:
            raise ValueError("benchmark iterations must be between 2 and 100")
        self.repository = repository
        self.embedding = embedding
        self.collection = collection
        self.service = service
        self.iterations = iterations
        self.k = k
        self.counter = DeterministicTokenCounter()
        self.evaluator = BenchmarkEvaluator(k=k)

    def _baseline(self, case: RelationBenchmarkCase, mode: str) -> dict:
        search = KnowledgeSearchService(
            repository=self.repository,
            embedding=self.embedding,
            collection=self.collection,
            score_threshold=0.55,
            retrieval_policy=KnowledgeRetrievalPolicy(mode=mode, max_records=50000),
        )
        # Same known anchors are available to all modes, including their text/context cost.
        seeds = [
            search.get(point_id=point_id, authority=current_authority())
            for point_id in case.request.seed_ids
        ]
        rows = search.search(query=case.baseline.query, limit=self.k, project=case.baseline.project)
        records = {}
        ordered = []
        for row in [*seeds, *rows]:
            if row is None:
                continue
            point_id = str(row["id"])
            record = {
                "id": point_id,
                "record_type": "knowledge",
                "text": self.counter.clip_to_tokens(row["content"], case.request.record_tokens),
                **{
                    key: row[key]
                    for key in ("entity_name", "topic", "version", "created_at", "project")
                    if key in row
                },
            }
            proposed = {**records, "knowledge:" + point_id: record}
            if (
                self.counter.estimate_tokens(json.dumps(proposed, ensure_ascii=False))
                > case.request.context_tokens
            ):
                continue
            records = proposed
            if point_id not in ordered:
                ordered.append(point_id)
        return {
            "records": records,
            "ordered_ids": ordered,
            "paths": [],
            "estimated_tokens": self.counter.estimate_tokens(
                json.dumps(records, ensure_ascii=False)
            ),
        }

    def run_case(self, case: RelationBenchmarkCase) -> dict:
        report: dict[str, Any] = {}
        seeds = {str(point_id) for point_id in case.request.seed_ids}
        for mode in ("vector", "hybrid", "relations"):
            if case.request.policy.as_of is not None and mode != "relations":
                report[mode] = {
                    "supported": False,
                    "reason": "ordinary Knowledge search has no historical as_of mode",
                }
                continue
            samples = []
            # One warm-up is excluded. Schema/index setup also occurs outside timed requests.
            for iteration in range(self.iterations + 1):
                self.repository.request_count = 0
                self.embedding.calls = 0
                started = perf_counter()
                output = (
                    self.service.recall(case.request)
                    if mode == "relations"
                    else self._baseline(case, mode)
                )
                elapsed = (perf_counter() - started) * 1000
                ids = (
                    list(dict.fromkeys(path["record_ids"][-1] for path in output["paths"]))
                    if mode == "relations"
                    else output["ordered_ids"]
                )
                ids = [point_id for point_id in ids if point_id not in seeds]
                texts = {row["id"]: row["text"] for row in output["records"].values()}
                times = {}
                for row in output["records"].values():
                    if "created_at" in row:
                        from datetime import datetime

                        times[row["id"]] = datetime.fromisoformat(
                            row["created_at"].replace("Z", "+00:00")
                        )
                metrics = self.evaluator.evaluate_case(
                    case.baseline,
                    [RankedHit(id=point_id, score=0.0) for point_id in ids],
                    text_by_id=texts,
                    event_time_by_id=times,
                    latency_ms=elapsed,
                )
                relevant = set(case.baseline.expected_ids) | set(case.baseline.acceptable_ids)
                precision = sum(point_id in relevant for point_id in ids) / len(ids) if ids else 0.0
                returned_paths = frozenset(tuple(path["record_ids"]) for path in output["paths"])
                path_precision = (
                    len(returned_paths & case.expected_paths) / len(returned_paths)
                    if returned_paths
                    else 0.0
                )
                path_recall = len(returned_paths & case.expected_paths) / len(case.expected_paths)
                if iteration:
                    samples.append(
                        {
                            "recall_at_k": metrics.recall_at_k,
                            "retrieval_precision": precision,
                            "contamination_rate": metrics.contamination_rate,
                            "temporal_correct": metrics.temporal_correct,
                            "latency_ms": elapsed,
                            "storage_calls": self.repository.request_count,
                            "embedding_calls": self.embedding.calls,
                            "context_tokens": output["estimated_tokens"],
                            "path_precision": path_precision if mode == "relations" else None,
                            "path_recall": path_recall if mode == "relations" else None,
                            "truncated": output.get("truncated", False),
                        }
                    )
            report[mode] = {
                "supported": True,
                "iterations": len(samples),
                **{
                    field: round(mean(sample[field] for sample in samples), 6)
                    for field in (
                        "recall_at_k",
                        "retrieval_precision",
                        "contamination_rate",
                        "storage_calls",
                        "embedding_calls",
                        "context_tokens",
                    )
                },
                "temporal_correct_rate": mean(sample["temporal_correct"] for sample in samples),
                "latency_p50_ms": round(percentile([s["latency_ms"] for s in samples], 0.5), 3),
                "latency_p95_ms": round(percentile([s["latency_ms"] for s in samples], 0.95), 3),
                "path_precision": samples[0]["path_precision"],
                "path_recall": samples[0]["path_recall"],
                "truncation_rate": mean(sample["truncated"] for sample in samples),
            }
        return {"case_id": case.baseline.case_id, "modes": report}
