# SPDX-License-Identifier: MPL-2.0
"""In-memory shadow registry for M4 candidate stability observation."""

from __future__ import annotations

from dataclasses import dataclass

from cyberbrain.core.metrics import MetricsRegistry

from .models import ConceptCandidate


@dataclass(frozen=True, slots=True)
class ConceptRegistryReport:
    candidate_count: int
    added_count: int
    removed_count: int
    stable_count: int
    changed_count: int
    candidate_ids: tuple[str, ...]


class ConceptShadowRegistry:
    """Observe candidate identity/support stability without durable persistence."""

    def __init__(self, *, metrics: MetricsRegistry | None = None) -> None:
        self._metrics = metrics or MetricsRegistry()
        self._previous: dict[str, tuple[str, str]] = {}

    def observe(
        self, candidates: list[ConceptCandidate] | tuple[ConceptCandidate, ...]
    ) -> ConceptRegistryReport:
        rows = tuple(candidates)
        ids = [item.candidate_concept_id for item in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("concept registry candidate IDs must be unique")
        current = {
            item.candidate_concept_id: (item.scope_marker, item.support_fingerprint)
            for item in rows
        }
        previous_ids = set(self._previous)
        current_ids = set(current)
        added = current_ids - previous_ids
        removed = previous_ids - current_ids
        stable = {
            candidate_id
            for candidate_id in current_ids & previous_ids
            if current[candidate_id] == self._previous[candidate_id]
        }
        changed = (current_ids & previous_ids) - stable

        self._metrics.increment("concept_shadow_observations_total")
        self._metrics.increment("concept_shadow_candidates_total", len(rows))
        self._metrics.increment("concept_shadow_added_total", len(added))
        self._metrics.increment("concept_shadow_removed_total", len(removed))
        self._metrics.increment("concept_shadow_stable_total", len(stable))
        self._metrics.increment("concept_shadow_changed_total", len(changed))
        self._previous = current

        return ConceptRegistryReport(
            candidate_count=len(rows),
            added_count=len(added),
            removed_count=len(removed),
            stable_count=len(stable),
            changed_count=len(changed),
            candidate_ids=tuple(sorted(current_ids)),
        )
