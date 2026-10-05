# SPDX-License-Identifier: MPL-2.0
"""Models for bounded reasoning: contradictions, typed inference, and counterfactual sandboxing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from cyberbrain.relations.models import RelationEdge


class ConflictType(StrEnum):
    DIRECT_CONTRADICTION = "direct_contradiction"
    POLARITY_MISMATCH = "polarity_mismatch"
    CAUSAL_CYCLE = "causal_cycle"


@dataclass(frozen=True, slots=True)
class ContradictionConflict:
    conflict_type: ConflictType
    source_edge: RelationEdge
    conflicting_edge: RelationEdge
    rationale: str


@dataclass(frozen=True, slots=True)
class DerivedAssertion:
    """An inferred relation that carries explicit provenance.

    Invariant: derived assertions are never automatically canonical truth.
    They remain marked provenance='derived_inference' and are not auto-promoted.
    """

    edge: RelationEdge
    rule: str
    premises: tuple[str, ...]
    confidence: float
    is_counterfactual: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CounterfactualSandboxResult:
    """Outcome of hypothetical sandbox evaluation without mutating storage."""

    hypothetical_edges_count: int
    base_edges_count: int
    contradictions: list[ContradictionConflict]
    derived_inferences: list[DerivedAssertion]
    is_consistent: bool
    summary: str
    is_incomplete: bool = False
