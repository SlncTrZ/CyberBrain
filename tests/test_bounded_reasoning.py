# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from cyberbrain.reasoning.engine import BoundedReasoningEngine
from cyberbrain.reasoning.models import ConflictType
from cyberbrain.relations.models import (
    EntityRef,
    EvidenceRef,
    RelationEdge,
    RelationKind,
    RelationScope,
    RelationStatus,
)

NOW = datetime(2026, 9, 9, 4, 0, tzinfo=UTC)


def _entity(name: str) -> EntityRef:
    return EntityRef(
        domain="engineering",
        topic="architecture",
        entity_type="module",
        entity_name=name,
        context={},
        scope=RelationScope(),
    )


def _edge(
    kind: RelationKind,
    src: EntityRef,
    tgt: EntityRef,
) -> RelationEdge:
    return RelationEdge(
        kind=kind,
        source=src,
        target=tgt,
        target_record_id=uuid4(),
        evidence=(EvidenceRef(record_type="knowledge", id=uuid4()),),
        status=RelationStatus.ACCEPTED,
        valid_from=NOW,
        review_note="Verified evidence",
    )


def test_contradiction_detection_polarity_mismatch() -> None:
    engine = BoundedReasoningEngine()
    ent_a = _entity("module_a")
    ent_b = _entity("module_b")

    base = [_edge(RelationKind.SUPPORTS, ent_a, ent_b)]
    cand = [_edge(RelationKind.CONTRADICTS, ent_a, ent_b)]

    conflicts = engine.detect_contradictions(cand, base)
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == ConflictType.POLARITY_MISMATCH
    assert conflicts[0].source_edge == cand[0]
    assert conflicts[0].conflicting_edge == base[0]


def test_contradiction_detection_structural_contradiction() -> None:
    engine = BoundedReasoningEngine()
    ent_a = _entity("component_x")
    ent_b = _entity("system_y")

    base = [_edge(RelationKind.PART_OF, ent_a, ent_b)]
    cand = [_edge(RelationKind.CONTRADICTS, ent_a, ent_b)]

    conflicts = engine.detect_contradictions(cand, base)
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == ConflictType.DIRECT_CONTRADICTION


def test_contradiction_detection_causal_cycle() -> None:
    engine = BoundedReasoningEngine()
    ent_a = _entity("event_a")
    ent_b = _entity("event_b")

    base = [_edge(RelationKind.CAUSES, ent_a, ent_b)]
    cand = [_edge(RelationKind.CAUSES, ent_b, ent_a)]

    conflicts = engine.detect_contradictions(cand, base)
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == ConflictType.CAUSAL_CYCLE


def test_derive_inferences_symmetric_contradiction() -> None:
    engine = BoundedReasoningEngine()
    ent_a = _entity("claim_a")
    ent_b = _entity("claim_b")
    uuid_a = uuid4()

    edge = _edge(RelationKind.CONTRADICTS, ent_a, ent_b)
    # Target anchor for ent_a supplied via source_record_ids (F08)
    derived = engine.derive_inferences([edge], source_record_ids={ent_a.key: uuid_a})

    assert len(derived) == 1
    inf = derived[0]
    assert inf.rule == "symmetric_contradiction"
    assert inf.premises == (edge.relation_id,)
    assert inf.edge.kind == RelationKind.CONTRADICTS
    assert inf.edge.source.entity_name == "claim_b"
    assert inf.edge.target.entity_name == "claim_a"
    assert inf.edge.target_record_id == uuid_a
    # Invariant: derived assertions are proposed, never auto-accepted
    assert inf.edge.status == RelationStatus.PROPOSED


def test_derive_inferences_transitive_dependency() -> None:
    engine = BoundedReasoningEngine()
    ent_a = _entity("service_a")
    ent_b = _entity("service_b")
    ent_c = _entity("database_c")

    edge_ab = _edge(RelationKind.DEPENDS_ON, ent_a, ent_b)
    edge_bc = _edge(RelationKind.DEPENDS_ON, ent_b, ent_c)

    derived = engine.derive_inferences([edge_ab, edge_bc])

    # Should infer service_a -> database_c
    dep_trans = [d for d in derived if d.rule == "transitive_dependency"]
    assert len(dep_trans) == 1
    inf = dep_trans[0]
    assert inf.edge.source.entity_name == "service_a"
    assert inf.edge.target.entity_name == "database_c"
    assert inf.edge.kind == RelationKind.DEPENDS_ON
    assert inf.edge.status == RelationStatus.PROPOSED
    # Union of evidence from both premises
    assert len(inf.edge.evidence) == 2


def test_counterfactual_sandbox_evaluation() -> None:
    engine = BoundedReasoningEngine()
    ent_a = _entity("feature_a")
    ent_b = _entity("feature_b")

    base = [_edge(RelationKind.SUPPORTS, ent_a, ent_b)]
    hypo_inconsistent = [_edge(RelationKind.CONTRADICTS, ent_a, ent_b)]

    sandbox_result = engine.evaluate_counterfactual(
        hypothetical_edges=hypo_inconsistent,
        base_edges=base,
    )

    assert not sandbox_result.is_consistent
    assert len(sandbox_result.contradictions) == 1
    assert sandbox_result.hypothetical_edges_count == 1
    assert sandbox_result.base_edges_count == 1
    # Derived inferences inside sandbox must be marked is_counterfactual
    assert all(inf.is_counterfactual for inf in sandbox_result.derived_inferences)
