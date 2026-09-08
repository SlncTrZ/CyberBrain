# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass

from .models import RankedHit


@dataclass(frozen=True, slots=True)
class PreRankedBaseline:
    """Backend-neutral adapter for already-ranked semantic/vector results."""

    ranked_ids: tuple[str, ...]

    def results(self) -> list[RankedHit]:
        return [
            RankedHit(
                id=record_id,
                score=round(1.0 / rank, 8),
                contributions={"baseline_rank": float(rank)},
            )
            for rank, record_id in enumerate(self.ranked_ids, start=1)
        ]
