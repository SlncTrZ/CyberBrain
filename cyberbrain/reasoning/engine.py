# SPDX-License-Identifier: MPL-2.0
"""Bounded reasoning: contradiction detection, typed inference, sandbox."""

from __future__ import annotations

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
    premise provenance and require human/admin review before promotion.
    """

    def detect_contradictions(
        self,
        candidate_edges: list[RelationEdge],
        existing_edges: list[RelationEdge],
    ) -> list[ContradictionConflict]:
        conflicts: list[ContradictionConflict] = []

        for cand in candidate_edges:
            cand_pair = self._endpoint_key(cand.source, cand.target)

            for exist in existing_edges:
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

        return conflicts

    def derive_inferences(
        self,
        edges: list[RelationEdge],
        *,
        max_depth: int = 2,
    ) -> list[DerivedAssertion]:
        derived: list[DerivedAssertion] = []
        seen_derived_keys: set[str] = set()

        # Rule 1: Symmetric contradiction
        # contradicts(A, B) => contradicts(B, A)
        for edge in edges:
            if edge.kind == RelationKind.CONTRADICTS:
                rev_key = f"contradicts:{self._endpoint_key(edge.target, edge.source)}"
                if rev_key not in seen_derived_keys:
                    seen_derived_keys.add(rev_key)
                    derived_edge = RelationEdge(
                        kind=RelationKind.CONTRADICTS,
                        source=edge.target,
                        target=edge.source,
                        target_record_id=edge.target_record_id,
                        evidence=tuple(edge.evidence),
                        status=RelationStatus.PROPOSED,
                        valid_from=edge.valid_from,
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

        # Rule 2: Transitive dependency (depth-bounded)
        # depends_on(A, B) & depends_on(B, C) => depends_on(A, C)
        depends_edges = [e for e in edges if e.kind == RelationKind.DEPENDS_ON]
        by_source: dict[str, list[RelationEdge]] = {}
        for e in depends_edges:
            src_key = self._entity_key(e.source)
            by_source.setdefault(src_key, []).append(e)

        for edge_ab in depends_edges:
            b_key = self._entity_key(edge_ab.target)
            next_edges = by_source.get(b_key, [])
            for edge_bc in next_edges:
                c_key = self._entity_key(edge_bc.target)
                a_key = self._entity_key(edge_ab.source)
                if a_key == c_key:
                    continue  # skip trivial cycle
                trans_key = f"depends_on:{a_key}->{c_key}"
                if trans_key not in seen_derived_keys:
                    seen_derived_keys.add(trans_key)
                    all_ev_map = {ev.id: ev for ev in (edge_ab.evidence + edge_bc.evidence)}
                    all_ev: tuple[EvidenceRef, ...] = tuple(all_ev_map.values())
                    derived_edge = RelationEdge(
                        kind=RelationKind.DEPENDS_ON,
                        source=edge_ab.source,
                        target=edge_bc.target,
                        target_record_id=edge_bc.target_record_id,
                        evidence=all_ev,
                        status=RelationStatus.PROPOSED,
                        valid_from=edge_ab.valid_from,
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

        return derived

    def evaluate_counterfactual(
        self,
        *,
        hypothetical_edges: list[RelationEdge],
        base_edges: list[RelationEdge],
    ) -> CounterfactualSandboxResult:
        """Evaluate hypothetical assertions in an isolated non-canonical sandbox."""
        contradictions = self.detect_contradictions(
            candidate_edges=hypothetical_edges,
            existing_edges=base_edges,
        )

        all_edges = base_edges + hypothetical_edges
        inferences = self.derive_inferences(all_edges)
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

        is_consistent = len(contradictions) == 0
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
            summary=summary,
        )

    @staticmethod
    def _endpoint_key(src: EntityRef, tgt: EntityRef) -> str:
        return (
            f"{src.domain}:{src.topic}:{src.entity_name}->"
            f"{tgt.domain}:{tgt.topic}:{tgt.entity_name}"
        )

    @staticmethod
    def _entity_key(entity: EntityRef) -> str:
        return f"{entity.domain}:{entity.topic}:{entity.entity_name}"
