# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from cyberbrain.dreaming.planner import TemporalBucket
from cyberbrain.dreaming.reasoner import EvidenceItem


class EvidenceRecall(Protocol):
    def recall(
        self,
        *,
        topic: str,
        bucket: TemporalBucket,
        limit: int,
    ) -> list[EvidenceItem]: ...


class BoundedAssociativeRecall:
    """Expands evidence through metadata-derived associations with a hard depth/budget cap."""

    def __init__(
        self,
        *,
        retriever: EvidenceRecall,
        max_depth: int = 2,
        per_query_limit: int = 3,
        total_limit: int = 12,
    ) -> None:
        if max_depth < 0 or max_depth > 2:
            raise ValueError("max_depth must be between 0 and 2")
        if per_query_limit < 1:
            raise ValueError("per_query_limit must be >= 1")
        if total_limit < 1:
            raise ValueError("total_limit must be >= 1")
        self._retriever = retriever
        self._max_depth = max_depth
        self._per_query_limit = per_query_limit
        self._total_limit = total_limit

    def expand(
        self,
        *,
        seed: list[EvidenceItem],
        bucket: TemporalBucket,
    ) -> list[EvidenceItem]:
        if self._max_depth == 0 or not seed:
            return []

        seen_ids = {item.id for item in seed}
        seen_queries: set[str] = set()
        frontier = list(seed)
        result: list[EvidenceItem] = []

        for depth in range(1, self._max_depth + 1):
            queries = self._association_queries(frontier, seen_queries)
            if not queries:
                break

            next_frontier: list[EvidenceItem] = []
            for query in queries:
                recalled = self._retriever.recall(
                    topic=query,
                    bucket=bucket,
                    limit=self._per_query_limit,
                )
                for item in recalled:
                    if item.id in seen_ids:
                        continue
                    seen_ids.add(item.id)
                    tagged = replace(
                        item,
                        metadata={
                            **item.metadata,
                            "association_depth": depth,
                            "association_query": query,
                        },
                    )
                    result.append(tagged)
                    next_frontier.append(tagged)
                    if len(result) >= self._total_limit:
                        return result
            frontier = next_frontier
            if not frontier:
                break

        return result

    @staticmethod
    def _association_queries(
        items: list[EvidenceItem],
        seen_queries: set[str],
    ) -> list[str]:
        queries: list[str] = []
        for item in items:
            for key in ("entity_name", "topic", "project"):
                value = str(item.metadata.get(key) or "").strip()
                normalized = value.casefold()
                if not value or normalized in seen_queries:
                    continue
                seen_queries.add(normalized)
                queries.append(value)
        return queries
