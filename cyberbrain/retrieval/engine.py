# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass

from .fusion import FusionCandidate, ReciprocalRankFusion
from .lexical import BM25Document, BM25Scorer
from .models import RankedHit, RetrievalHit


@dataclass(frozen=True, slots=True)
class HybridQueryResult:
    semantic: tuple[RankedHit, ...]
    lexical: tuple[RankedHit, ...]
    hybrid: tuple[RankedHit, ...]


class HybridRetrievalEngine:
    """Pure in-memory Wave-1 engine for benchmarking deterministic fusion."""

    def __init__(
        self, hits: list[RetrievalHit], *, fusion: ReciprocalRankFusion | None = None
    ) -> None:
        self._hits = {hit.id: hit for hit in hits}
        self._lexical = BM25Scorer([BM25Document(hit.id, hit.text) for hit in hits])
        self._fusion = fusion or ReciprocalRankFusion()

    def query(
        self,
        query: str,
        *,
        semantic_ranked_ids: tuple[str, ...] = (),
        project: str | None = None,
        topic: str | None = None,
        entity_name: str | None = None,
        status: str | None = None,
        not_after=None,
    ) -> HybridQueryResult:
        semantic = [
            RankedHit(
                id=record_id,
                score=round(1.0 / rank, 8),
                contributions={"semantic_rank": float(rank)},
            )
            for rank, record_id in enumerate(semantic_ranked_ids, start=1)
            if record_id in self._hits
        ]
        lexical_pairs = self._lexical.score(query)
        lexical = [
            RankedHit(id=record_id, score=score, contributions={"bm25": score})
            for record_id, score in lexical_pairs
            if score > 0
        ]

        semantic_rank = {item.id: rank for rank, item in enumerate(semantic, start=1)}
        lexical_rank = {item.id: rank for rank, item in enumerate(lexical, start=1)}
        ids = set(semantic_rank) | set(lexical_rank)
        candidates = [
            FusionCandidate(
                hit=self._hits[record_id],
                semantic_rank=semantic_rank.get(record_id),
                lexical_rank=lexical_rank.get(record_id),
            )
            for record_id in sorted(ids)
        ]
        hybrid = self._fusion.fuse(
            candidates,
            project=project,
            topic=topic,
            entity_name=entity_name,
            status=status,
            not_after=not_after,
        )
        return HybridQueryResult(tuple(semantic), tuple(lexical), tuple(hybrid))
