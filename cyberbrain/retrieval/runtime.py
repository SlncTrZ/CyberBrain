# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from cyberbrain.core.errors import StorageError
from cyberbrain.storage.base import PointRepository

from .fusion import FusionCandidate, ReciprocalRankFusion
from .lexical import BM25Corpus, BM25Document
from .literal import literal_heavy_query
from .models import RetrievalHit

RetrievalMode = Literal["vector", "literal", "hybrid"]


@dataclass(frozen=True, slots=True)
class KnowledgeRetrievalPolicy:
    mode: RetrievalMode = "vector"
    max_records: int = 10_000
    candidate_multiplier: int = 3

    def __post_init__(self) -> None:
        if self.mode not in {"vector", "literal", "hybrid"}:
            raise ValueError("unknown Knowledge retrieval mode")
        if not 1 <= self.max_records <= 50_000:
            raise ValueError("retrieval max_records must be between 1 and 50000")
        if not 1 <= self.candidate_multiplier <= 10:
            raise ValueError("retrieval candidate_multiplier must be between 1 and 10")

    def uses_lexical(self, query: str) -> bool:
        return self.mode == "hybrid" or (
            self.mode == "literal" and literal_heavy_query(query)
        )

    def candidate_limit(self, limit: int) -> int:
        return max(limit, min(500, limit * self.candidate_multiplier))


def rank_knowledge(
    *,
    repository: PointRepository,
    collection: str,
    query: str,
    vector_points: list[dict[str, Any]],
    qdrant_filter: dict[str, Any],
    limit: int,
    policy: KnowledgeRetrievalPolicy,
) -> list[dict[str, Any]]:
    """Rank a fresh, storage-filtered corpus; never cache across authorities.

    The caller supplies the SAME lifecycle/identity filter as semantic search.
    Refuse a truncated lexical corpus, and revalidate selected IDs in storage
    before projection so lifecycle changes cannot resurrect a cached record.
    """
    points = repository.scroll(
        collection, qdrant_filter=qdrant_filter, limit=policy.max_records + 1,
    )
    if len(points) > policy.max_records:
        raise StorageError("Knowledge lexical corpus exceeds configured max_records")
    corpus = BM25Corpus([
        BM25Document(str(point["id"]), str((point.get("payload") or {}).get("content") or ""))
        for point in points
    ])
    lexical = [
        (point_id, score) for point_id, score in corpus.score(query) if score > 0
    ][:policy.candidate_limit(limit)]
    semantic_ids = list(dict.fromkeys(str(point["id"]) for point in vector_points))
    lexical_ids = [point_id for point_id, _score in lexical]
    semantic_by_id = {str(point["id"]): point for point in vector_points}
    lexical_scores = dict(lexical)
    ranking_scores: dict[str, float] = {}

    if policy.mode == "hybrid":
        semantic_ranks = {point_id: rank for rank, point_id in enumerate(semantic_ids, 1)}
        lexical_ranks = {point_id: rank for rank, point_id in enumerate(lexical_ids, 1)}
        ranked = ReciprocalRankFusion().fuse([
            FusionCandidate(
                hit=RetrievalHit(id=point_id),
                semantic_rank=semantic_ranks.get(point_id),
                lexical_rank=lexical_ranks.get(point_id),
            )
            for point_id in sorted(set(semantic_ids) | set(lexical_ids))
        ])
        ordered_ids = [hit.id for hit in ranked]
        ranking_scores = {hit.id: hit.score for hit in ranked}
    else:
        # Reuse the reviewed literal route. Zero-overlap rows never displace
        # semantic evidence; fill any remaining slots from semantic candidates.
        ordered_ids = list(dict.fromkeys([*lexical_ids, *semantic_ids]))

    selected_ids = ordered_ids[:limit]
    if not selected_ids:
        return []
    current_filter = {
        **qdrant_filter,
        "must": [*qdrant_filter.get("must", []), {"has_id": selected_ids}],
    }
    current_points = repository.scroll(
        collection, qdrant_filter=current_filter, limit=len(selected_ids),
    )
    current_by_id = {str(point["id"]): point for point in current_points}
    rows = []
    for point_id in selected_ids:
        point = current_by_id.get(point_id)
        if point is None:
            continue
        rows.append({
            **(point.get("payload") or {}),
            "id": point_id,
            # Cosine score stays cosine; lexical-only evidence has no cosine.
            "score": semantic_by_id.get(point_id, {}).get("score"),
            "_retrieval": {
                "method": policy.mode,
                "ranking_score": ranking_scores.get(point_id),
                "lexical_score": lexical_scores.get(point_id),
            },
        })
    return rows
