# SPDX-License-Identifier: MPL-2.0
"""Bounded reasoning: contradiction detection, typed inference, sandbox."""

from __future__ import annotations

from uuid import UUID

from cyberbrain.reasoning.models import (
    ConflictType,
    ContradictionConflict,
    CounterfactualSandboxResult,
    DerivedAssertion,
)
from cyberbrain.relations.models import (
    EntityRef,
    EvidenceRef,
    RelationEdge,
    RelationKind,
    RelationStatus,
)


class BoundedReasoningEngine:
    """Bounded, deterministic inference and contradiction detection over typed relations.

    Core Invariant: Derived assertions are NOT canonical truth. They carry explicit
    premise provenance, inherit intersection of validity intervals, and require review.
    """

    def __init__(
        self,
        *,
        max_inferences: int = 100,
        max_comparisons: int = 10_000,
    ) -> None:
        self._max_inferences = max_inferences
        self._max_comparisons = max_comparisons

    def detect_contradictions(
        self,
        candidate_edges: list[RelationEdge],
        existing_edges: list[RelationEdge],
    ) -> list[ContradictionConflict]:
        conflicts, _ = self._detect_contradictions_bounded(candidate_edges, existing_edges)
        return conflicts

    def _detect_contradictions_bounded(
        self,
        candidate_edges: list[RelationEdge],
        existing_edges: list[RelationEdge],
    ) -> tuple[list[ContradictionConflict], bool]:
        conflicts: list[ContradictionConflict] = []
        comparisons = 0
        budget_exceeded = False

        for cand in candidate_edges:
            cand_pair = self._endpoint_key(cand.source, cand.target)

            for exist in existing_edges:
                comparisons += 1
                if comparisons > self._max_comparisons:
                    budget_exceeded = True
                    break
                if cand.relation_id and cand.relation_id == exist.relation_id:
                    continue
                exist_pair = self._endpoint_key(exist.source, exist.target)
                exist_rev = self._endpoint_key(exist.target, exist.source)

                # Check 1: supports vs contradicts
                if (cand_pair == exist_pair or cand_pair == exist_rev) and (
                    (cand.kind == RelationKind.SUPPORTS and exist.kind == RelationKind.CONTRADICTS)
                    or (
                        cand.kind == RelationKind.CONTRADICTS
                        and exist.kind == RelationKind.SUPPORTS
                    )
                ):
                    conflicts.append(
                        ContradictionConflict(
                            conflict_type=ConflictType.POLARITY_MISMATCH,
                            source_edge=cand,
                            conflicting_edge=exist,
                            rationale=(
                                f"Polarity mismatch: '{cand.source.entity_name}' {cand.kind.value} "
                                f"'{cand.target.entity_name}' contradicts {exist.kind.value}."
                            ),
                        )
                    )

                # Check 2: structural relation (part_of) vs contradicts
                if (cand_pair == exist_pair or cand_pair == exist_rev) and (
                    (cand.kind == RelationKind.PART_OF and exist.kind == RelationKind.CONTRADICTS)
                    or (
                        cand.kind == RelationKind.CONTRADICTS
                        and exist.kind == RelationKind.PART_OF
                    )
                ):
                    conflicts.append(
                        ContradictionConflict(
                            conflict_type=ConflictType.DIRECT_CONTRADICTION,
                            source_edge=cand,
                            conflicting_edge=exist,
                            rationale=(
                                f"Direct structural contradiction between part_of and contradicts "
                                f"for '{cand.source.entity_name}' and '{cand.target.entity_name}'."
                            ),
                        )
                    )

                # Check 3: direct causal cycle
                if cand.kind == RelationKind.CAUSES and exist.kind == RelationKind.CAUSES:
                    if cand_pair == exist_rev:
                        conflicts.append(
                            ContradictionConflict(
                                conflict_type=ConflictType.CAUSAL_CYCLE,
                                source_edge=cand,
                                conflicting_edge=exist,
                                rationale=(
                                    f"Direct causal cycle: '{cand.source.entity_name}' causes "
                                    f"'{cand.target.entity_name}' while target causes source."
                                ),
                            )
                        )

            if budget_exceeded:
                break

        return conflicts, budget_exceeded

    def derive_inferences(
        self,
        edges: list[RelationEdge],
        *,
        max_depth: int = 2,
        source_record_ids: dict[str, UUID] | None = None,
    ) -> list[DerivedAssertion]:
        derived, _ = self._derive_inferences_bounded(
            edges, max_depth=max_depth, source_record_ids=source_record_ids
        )
        return derived

    def _derive_inferences_bounded(
        self,
        edges: list[RelationEdge],
        *,
        max_depth: int = 2,
        source_record_ids: dict[str, UUID] | None = None,
    ) -> tuple[list[DerivedAssertion], bool]:
        if not 0 <= max_depth <= 5:
            raise ValueError("max_depth must be between 0 and 5")
        if max_depth == 0:
            return [], False

        # Reject any premise that is explicitly rejected (F04)
        eligible = [e for e in edges if e.status != RelationStatus.REJECTED]
        derived: list[DerivedAssertion] = []
        seen_derived_keys: set[str] = set()
        budget_exceeded = False
        comparisons = 0

        # Map known target entity keys to their verified record IDs
        known_record_ids: dict[str, UUID] = dict(source_record_ids or {})
        for e in eligible:
            known_record_ids[e.target.key] = e.target_record_id

        # Rule 1: Symmetric contradiction (depth >= 1)
        # contradicts(A, B) => contradicts(B, A)
        for edge in eligible:
            comparisons += 1
            if len(derived) >= self._max_inferences or comparisons > self._max_comparisons:
                budget_exceeded = True
                break
            if edge.kind == RelationKind.CONTRADICTS:
                # F08: Target of reversed edge is edge.source.
                # Must have verified target_record_id anchor for edge.source!
                target_anchor = known_record_ids.get(edge.source.key)
                if target_anchor is None:
                    continue

                rev_key = f"contradicts:{self._endpoint_key(edge.target, edge.source)}"
                if rev_key not in seen_derived_keys:
                    seen_derived_keys.add(rev_key)
                    derived_edge = RelationEdge(
                        kind=RelationKind.CONTRADICTS,
                        source=edge.target,
                        target=edge.source,
                        target_record_id=target_anchor,
                        evidence=tuple(edge.evidence),
                        status=RelationStatus.PROPOSED,
                        valid_from=edge.valid_from,
                        valid_until=edge.valid_until,
                        review_note=(
                            "Derived symmetric contradiction from premise edge "
                            f"{edge.relation_id or 'hypothetical'}"
                        ),
                    )
                    derived.append(
                        DerivedAssertion(
                            edge=derived_edge,
                            rule="symmetric_contradiction",
                            premises=(edge.relation_id or "hypothetical",),
                            confidence=0.85,
                        )
                    )

        # Rule 2: Transitive dependency (requires depth >= 2)
        # depends_on(A, B) & depends_on(B, C) => depends_on(A, C)
        if max_depth >= 2 and not budget_exceeded:
            depends_edges = [e for e in eligible if e.kind == RelationKind.DEPENDS_ON]
            by_source: dict[str, list[RelationEdge]] = {}
            for e in depends_edges:
                src_key = self._entity_key(e.source)
                by_source.setdefault(src_key, []).append(e)

            for edge_ab in depends_edges:
                if len(derived) >= self._max_inferences or comparisons > self._max_comparisons:
                    budget_exceeded = True
                    break
                b_key = self._entity_key(edge_ab.target)
                next_edges = by_source.get(b_key, [])
                for edge_bc in next_edges:
                    comparisons += 1
                    if len(derived) >= self._max_inferences or comparisons > self._max_comparisons:
                        budget_exceeded = True
                        break
                    c_key = self._entity_key(edge_bc.target)
                    a_key = self._entity_key(edge_ab.source)
                    if a_key == c_key:
                        continue  # skip trivial self-cycle

                    # Check temporal interval intersection (F04)
                    valid_from = max(edge_ab.valid_from, edge_bc.valid_from)
                    valid_until = None
                    if edge_ab.valid_until is not None and edge_bc.valid_until is not None:
                        valid_until = min(edge_ab.valid_until, edge_bc.valid_until)
                    elif edge_ab.valid_until is not None:
                        valid_until = edge_ab.valid_until
                    elif edge_bc.valid_until is not None:
                        valid_until = edge_bc.valid_until

                    if valid_until is not None and valid_until <= valid_from:
                        # Disjoint validity intervals; cannot infer dependency
                        continue

                    trans_key = f"depends_on:{a_key}->{c_key}"
                    if trans_key not in seen_derived_keys:
                        seen_derived_keys.add(trans_key)
                        all_ev_map = {
                            (ev.record_type, ev.id): ev
                            for ev in (edge_ab.evidence + edge_bc.evidence)
                        }
                        if len(all_ev_map) > 32:
                            # F09: Capacity exceeded: refuse to derive assertion; do NOT cut proofs
                            budget_exceeded = True
                            continue
                        all_ev: tuple[EvidenceRef, ...] = tuple(all_ev_map.values())
                        derived_edge = RelationEdge(
                            kind=RelationKind.DEPENDS_ON,
                            source=edge_ab.source,
                            target=edge_bc.target,
                            target_record_id=edge_bc.target_record_id,
                            evidence=all_ev,
                            status=RelationStatus.PROPOSED,
                            valid_from=valid_from,
                            valid_until=valid_until,
                            review_note=(
                                f"Derived transitive dependency via '{edge_ab.target.entity_name}' "
                                f"from premises ({edge_ab.relation_id or 'e1'}, "
                                f"{edge_bc.relation_id or 'e2'})"
                            ),
                        )
                        derived.append(
                            DerivedAssertion(
                                edge=derived_edge,
                                rule="transitive_dependency",
                                premises=(
                                    edge_ab.relation_id or "premise_ab",
                                    edge_bc.relation_id or "premise_bc",
                                ),
                                confidence=0.75,
                            )
                        )

        return derived, budget_exceeded

    def evaluate_counterfactual(
        self,
        *,
        hypothetical_edges: list[RelationEdge],
        base_edges: list[RelationEdge],
    ) -> CounterfactualSandboxResult:
        """Evaluate hypothetical assertions in an isolated non-canonical sandbox."""
        contradictions, base_budget_hit = self._detect_contradictions_bounded(
            candidate_edges=hypothetical_edges,
            existing_edges=base_edges,
        )

        # Internal conflict detection within hypothetical_edges (F03)
        internal_conflicts, internal_budget_hit = self._detect_contradictions_bounded(
            candidate_edges=hypothetical_edges,
            existing_edges=hypothetical_edges,
        )
        seen_conflict_keys = {
            (c.conflict_type, c.source_edge.relation_id, c.conflicting_edge.relation_id)
            for c in contradictions
        }
        for c in internal_conflicts:
            k1 = (c.conflict_type, c.source_edge.relation_id, c.conflicting_edge.relation_id)
            k2 = (c.conflict_type, c.conflicting_edge.relation_id, c.source_edge.relation_id)
            if k1 not in seen_conflict_keys and k2 not in seen_conflict_keys:
                seen_conflict_keys.add(k1)
                contradictions.append(c)

        all_edges = base_edges + hypothetical_edges
        inferences, inference_budget_hit = self._derive_inferences_bounded(all_edges)
        counterfactual_inferences = [
            DerivedAssertion(
                edge=inf.edge,
                rule=inf.rule,
                premises=inf.premises,
                confidence=inf.confidence,
                is_counterfactual=True,
            )
            for inf in inferences
        ]

        budget_exceeded = base_budget_hit or internal_budget_hit or inference_budget_hit
        if budget_exceeded:
            is_consistent = False
            is_incomplete = True
            summary = (
                "Counterfactual sandbox incomplete: evaluation budget exceeded. "
                "Cannot conclude consistent. "
                f"{len(contradictions)} contradiction(s) detected, "
                f"{len(counterfactual_inferences)} derived inference(s) generated."
            )
        else:
            is_consistent = len(contradictions) == 0
            is_incomplete = False
            summary = (
                f"Counterfactual sandbox consistent: {is_consistent}. "
                f"{len(contradictions)} contradiction(s) detected, "
                f"{len(counterfactual_inferences)} derived inference(s) generated."
            )

        return CounterfactualSandboxResult(
            hypothetical_edges_count=len(hypothetical_edges),
            base_edges_count=len(base_edges),
            contradictions=contradictions,
            derived_inferences=counterfactual_inferences,
            is_consistent=is_consistent,
            is_incomplete=is_incomplete,
            summary=summary,
        )

    @staticmethod
    def _endpoint_key(src: EntityRef, tgt: EntityRef) -> str:
        # Canonical entity identity including scope/context (F05)
        return f"{src.key}->{tgt.key}"

    @staticmethod
    def _entity_key(entity: EntityRef) -> str:
        # Canonical entity identity including scope/context (F05)
        return entity.key
