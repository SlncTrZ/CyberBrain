# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass, field

from .models import RankedHit, RetrievalHit
from .signals import ScopeTemporalSignals


@dataclass(frozen=True, slots=True)
class FusionCandidate:
    hit: RetrievalHit
    semantic_rank: int | None = None
    lexical_rank: int | None = None


@dataclass(frozen=True, slots=True)
class ReciprocalRankFusion:
    rank_constant: int = 60
    semantic_weight: float = 1.0
    lexical_weight: float = 1.0
    signals: ScopeTemporalSignals = field(default_factory=ScopeTemporalSignals)

    def __post_init__(self) -> None:
        if self.rank_constant < 1:
            raise ValueError("rank_constant must be positive")
        if self.semantic_weight < 0 or self.lexical_weight < 0:
            raise ValueError("channel weights must not be negative")

    def fuse(
        self,
        candidates: list[FusionCandidate],
        *,
        project: str | None = None,
        topic: str | None = None,
        entity_name: str | None = None,
        status: str | None = None,
        not_after=None,
    ) -> list[RankedHit]:
        merged: dict[str, tuple[RetrievalHit, dict[str, float]]] = {}
        for candidate in candidates:
            hit = candidate.hit
            allowed, signal_parts = self.signals.contributions(
                hit,
                project=project,
                topic=topic,
                entity_name=entity_name,
                status=status,
                not_after=not_after,
            )
            if not allowed:
                continue
            current = merged.setdefault(hit.id, (hit, {}))[1]
            if candidate.semantic_rank is not None:
                current["semantic_rrf"] = max(
                    current.get("semantic_rrf", 0.0),
                    self.semantic_weight / (self.rank_constant + candidate.semantic_rank),
                )
            if candidate.lexical_rank is not None:
                current["lexical_rrf"] = max(
                    current.get("lexical_rrf", 0.0),
                    self.lexical_weight / (self.rank_constant + candidate.lexical_rank),
                )
            for key, value in signal_parts.items():
                current[key] = max(current.get(key, 0.0), value)

        ranked = [
            RankedHit(id=doc_id, score=round(sum(parts.values()), 8), contributions=dict(parts))
            for doc_id, (_hit, parts) in merged.items()
        ]
        ranked.sort(key=lambda item: (-item.score, item.id))
        return ranked
