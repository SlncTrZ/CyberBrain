# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from cyberbrain.core.errors import ConfigurationError, StorageError
from cyberbrain.knowledge.evolution import EvolutionOutcome, KnowledgeEvolutionService
from cyberbrain.relations import EntityRef, EvidenceRef, RelationEdge
from cyberbrain.schemas.models import KnowledgeRecord, KnowledgeRecordClass
from cyberbrain.tenancy import OperationClass, bind_authority
from tests.tenancy.test_runtime_enforcement import CountingEmbedding, authority
from tests.test_evolution import FakeRepository


class Repository(FakeRepository):
    def __init__(self):
        super().__init__()
        self.collections = {}
        self.reads = []
        self.fail_activation = False

    def upsert(self, collection, *, point_id, vector, payload):
        super().upsert(collection, point_id=point_id, vector=vector, payload=payload)
        self.collections[point_id] = collection

    @staticmethod
    def _matches(payload, condition):
        if "should" in condition:
            return any(Repository._matches(payload, child) for child in condition["should"])
        if "is_empty" in condition:
            return payload.get(condition["is_empty"]["key"]) is None
        value = payload
        for part in condition["key"].split("."):
            value = value.get(part) if isinstance(value, dict) else None
        match = condition["match"]
        return value == match["value"] if "value" in match else value in match["any"]

    def retrieve(self, collection, point_id, *, qdrant_filter=None):
        self.reads.append(deepcopy(qdrant_filter))
        point = self.points.get(point_id)
        if point is None or self.collections[point_id] != collection:
            return None
        if not all(
            self._matches(point["payload"], c) for c in (qdrant_filter or {}).get("must", [])
        ):
            return None
        return deepcopy(point)

    def scroll(self, collection, *, qdrant_filter=None, limit=100):
        return [
            deepcopy(p)
            for key, p in self.points.items()
            if self.collections[key] == collection
            and all(self._matches(p["payload"], c) for c in (qdrant_filter or {}).get("must", []))
        ][:limit]

    def set_payload(self, collection, *, point_id, payload):
        if self.fail_activation and payload.get("status") == "active":
            self.fail_activation = False
            raise StorageError("injected activation failure")
        super().set_payload(collection, point_id=point_id, payload=payload)


def setup():
    repo = Repository()
    embedding = CountingEmbedding()
    evolution = KnowledgeEvolutionService(
        repository=repo,
        embedding=embedding,
        collection="knowledge",
        episodic_collection="episode",
    )
    common = dict(
        domain="engineering",
        topic="dependencies",
        entity_type="component",
        tenant="t",
        user="u",
        agent="a",
        project="p",
    )
    target = evolution.store(content="Database component.", entity_name="database", **common).record
    source = EntityRef.from_payload({**common, "entity_name": "api"})
    edge = RelationEdge(
        kind="depends_on",
        source=source,
        target=EntityRef.from_payload(target.model_dump(mode="json")),
        target_record_id=target.id,
        evidence=(EvidenceRef(record_type="knowledge", id=target.id),),
        valid_from=datetime(2026, 10, 1, tzinfo=UTC),
    )
    return SimpleNamespace(
        repo=repo,
        embedding=embedding,
        evolution=evolution,
        common=common,
        target=target,
        edge=edge,
    )


def raw(edge, **changes):
    value = edge.model_dump(mode="json")
    value.update(changes)
    return {"schema_version": 1, "edges": [value]}


def store(state, bundle=None, **changes):
    args = dict(content="API component.", entity_name="api", **state.common)
    if bundle is not None:
        args["extensions"] = {"relations": bundle}
    args.update(changes)
    return state.evolution.store(**args)


def owner():
    return authority(tenant="t", user="u", agent="a", project="p")


def test_relation_only_change_versions_knowledge_and_exact_retry_is_idempotent():
    state = setup()
    first = store(state)
    linked = store(state, raw(state.edge))
    retry = store(state, raw(state.edge))
    assert linked.outcome == EvolutionOutcome.EVOLVE
    assert linked.record.content_hash == first.record.content_hash
    assert linked.record.version == 2
    assert retry.outcome == EvolutionOutcome.NO_CHANGE
    assert retry.record.id == linked.record.id
    assert state.repo.points[first.record.id]["payload"]["status"] == "superseded"
    assert state.repo.points[first.record.id]["payload"]["extensions"].get("relations") is None
    assert (
        KnowledgeRecord.model_validate(linked.record.model_dump(mode="json")).id == linked.record.id
    )


def test_explicit_empty_bundle_withdraws_proposed_edges_but_omitted_exact_retry_preserves():
    state = setup()
    first = store(state, raw(state.edge))
    assert store(state).record.id == first.record.id
    cleared = store(state, {"schema_version": 1, "edges": []})
    assert cleared.record.version == 2
    assert cleared.record.extensions["relations"]["edges"] == []


def test_content_change_does_not_silently_inherit_old_relations():
    state = setup()
    first = store(state, raw(state.edge))
    next_record = store(state, content="Different API design.").record
    assert next_record.supersedes_id == first.record.id
    assert "relations" not in next_record.extensions


@pytest.mark.parametrize("status", ["accepted", "rejected"])
def test_reviewed_state_requires_authenticated_review_grant(status):
    state = setup()
    bundle = raw(state.edge, status=status, review_note="Owner reviewed the cited assertion.")
    for caller in [
        None,
        authority(
            tenant="t",
            user="u",
            agent="a",
            project="p",
            operations={OperationClass.READ, OperationClass.WRITE},
        ),
    ]:
        before = state.embedding.calls
        if caller is None:
            with pytest.raises(ConfigurationError, match="admin_review"):
                store(state, bundle)
        else:
            with bind_authority(caller), pytest.raises(ConfigurationError, match="admin_review"):
                store(state, bundle)
        assert state.embedding.calls == before
        assert len(state.repo.points) == 1
    with bind_authority(owner()):
        accepted = store(state, bundle)
        retry = store(state, bundle)
    assert accepted.record.extensions["relations"]["edges"][0]["status"] == status
    assert retry.record.id == accepted.record.id


@pytest.mark.parametrize(
    "change",
    [
        {"bundle": {"schema_version": 1, "edges": []}},
        {"content": "Changed knowledge."},
        {"force_evolution": True},
    ],
)
def test_author_cannot_bypass_review_by_removing_a_reviewed_edge(change):
    state = setup()
    with bind_authority(owner()):
        first = store(state, raw(state.edge, status="accepted", review_note="Explicit review."))
    author = authority(
        tenant="t",
        user="u",
        agent="a",
        project="p",
        operations={OperationClass.READ, OperationClass.WRITE},
    )
    with bind_authority(author), pytest.raises(ConfigurationError, match="admin_review"):
        store(state, **change)
    assert state.repo.points[first.record.id]["payload"]["status"] == "active"


@pytest.mark.parametrize("bad_id", [UUID(int=100), UUID(int=101)])
def test_foreign_and_absent_evidence_are_indistinguishable_and_never_write(bad_id):
    state = setup()
    state.evolution.store(
        content="Foreign evidence.",
        entity_name="foreign",
        **{**state.common, "tenant": "foreign"},
    )
    foreign_id = next(
        key
        for key, point in state.repo.points.items()
        if point["payload"].get("tenant") == "foreign"
    )
    chosen = foreign_id if bad_id.int == 100 else bad_id
    bundle = raw(state.edge, evidence=[{"record_type": "knowledge", "id": str(chosen)}])
    before = state.embedding.calls
    with bind_authority(owner()), pytest.raises(ConfigurationError) as caught:
        store(state, bundle)
    assert str(caught.value) == "relation endpoint or evidence unavailable"
    assert state.embedding.calls == before
    assert len(state.repo.points) == 2
    assert all(query is not None for query in state.repo.reads)


def test_target_version_anchor_must_match_identity_and_still_be_active():
    state = setup()
    updated_target = state.evolution.store(
        content="New Database design.",
        entity_name="database",
        **state.common,
    ).record
    with pytest.raises(ConfigurationError, match="unavailable"):
        store(state, raw(state.edge))
    changed = raw(state.edge, target_record_id=str(updated_target.id))
    linked = store(state, changed)
    assert (
        linked.record.extensions["relations"]["edges"][0]["relation_id"] == state.edge.relation_id
    )
    wrong_identity = raw(state.edge)
    wrong_identity["edges"][0]["target"]["entity_name"] = "different"
    wrong_identity["edges"][0]["relation_id"] = None
    wrong_identity["edges"][0]["target_record_id"] = str(updated_target.id)
    with pytest.raises(ConfigurationError, match="unavailable"):
        store(state, wrong_identity)


def test_source_and_target_partition_cannot_be_forged():
    state = setup()
    changed = raw(state.edge)
    changed["edges"][0]["source"]["scope"]["project"] = "other"
    changed["edges"][0]["relation_id"] = None
    with pytest.raises(ConfigurationError):
        store(state, changed)
    changed = raw(state.edge)
    changed["edges"][0]["target"]["scope"]["tenant"] = "foreign"
    changed["edges"][0]["relation_id"] = None
    with pytest.raises(ConfigurationError):
        store(state, changed)
    assert len(state.repo.points) == 1


@pytest.mark.parametrize("operations", [{OperationClass.WRITE}, {OperationClass.READ}])
def test_read_and_write_grants_are_both_required_before_relation_writes(operations):
    state = setup()
    before = state.embedding.calls
    with (
        bind_authority(
            authority(
                tenant="t",
                user="u",
                agent="a",
                project="p",
                operations=operations,
            )
        ),
        pytest.raises(ConfigurationError),
    ):
        store(state, raw(state.edge))
    assert state.embedding.calls == before
    assert not state.repo.reads


def test_episode_evidence_uses_configured_collection_and_preserves_historical_session():
    state = setup()
    from cyberbrain.memory.service import MemoryService

    episode = MemoryService(
        repository=state.repo,
        embedding=state.embedding,
        collection="episode",
    ).store(
        content="Explicit dependency observation.",
        session_id="historical",
        event_time=datetime(2026, 10, 1, tzinfo=UTC),
        tenant="t",
        user="u",
        agent="a",
        project="p",
    )
    evidence_id = episode.id
    bundle = raw(state.edge, evidence=[{"record_type": "episode", "id": str(evidence_id)}])
    with bind_authority(owner()):
        record = store(state, bundle).record
    assert record.extensions["relations"]["edges"][0]["evidence"][0]["id"] == str(evidence_id)


def test_relation_namespace_cannot_be_put_on_self_model_records():
    state = setup()
    with pytest.raises(ConfigurationError, match="canonical Knowledge"):
        store(state, raw(state.edge), record_class=KnowledgeRecordClass.SELF_MODEL_HYPOTHESIS)


def test_existing_evolution_recovery_preserves_relation_change_after_restart():
    state = setup()
    first = store(state)
    state.repo.fail_activation = True
    with pytest.raises(StorageError):
        store(state, raw(state.edge))
    assert state.repo.points[first.record.id]["payload"]["status"] == "superseded"
    restarted = KnowledgeEvolutionService(
        repository=state.repo,
        embedding=state.embedding,
        collection="knowledge",
        episodic_collection="episode",
    )
    state.evolution = restarted
    recovered = store(state, raw(state.edge))
    assert recovered.outcome == EvolutionOutcome.NO_CHANGE
    assert recovered.record.version == 2
    assert (
        recovered.record.extensions["relations"]["edges"][0]["relation_id"]
        == state.edge.relation_id
    )
    assert (
        len(
            [
                p
                for p in state.repo.points.values()
                if p["payload"]["entity_name"] == "api" and p["payload"]["status"] == "active"
            ]
        )
        == 1
    )


def test_mcp_existing_knowledge_store_can_persist_proposed_relations(monkeypatch):
    import asyncio
    import json

    import cyberbrain.mcp.server as server

    state = setup()
    monkeypatch.setattr(server, "_runtime", SimpleNamespace(knowledge_evolution=state.evolution))
    args = dict(
        content="API component.",
        entity_name="api",
        **state.common,
        extensions={"relations": raw(state.edge)},
    )
    with bind_authority(owner()):
        result = asyncio.run(server.call_tool("knowledge_store", args))
    response = json.loads(result[0].text)
    assert response["record"]["extensions"]["relations"]["edges"][0]["status"] == "proposed"
    assert response["record"]["version"] == 1


def test_rejection_can_preserve_historical_anchor_after_target_is_superseded():
    state = setup()
    with bind_authority(owner()):
        first = store(state, raw(state.edge, status="accepted", review_note="Reviewed."))
        state.evolution.store(
            content="Database design changed.",
            entity_name="database",
            **state.common,
        )
        rejected = store(
            state, raw(state.edge, status="rejected", review_note="Dependency obsolete.")
        )
    assert rejected.record.version == first.record.version + 1
    assert rejected.record.extensions["relations"]["edges"][0]["target_record_id"] == str(
        state.target.id
    )


def test_explicit_relation_context_cannot_alias_a_previous_node_via_numeric_equality():
    state = setup()
    state.common["context"] = {"value": 1}
    state.edge = state.edge.model_copy(
        update={
            "source": EntityRef.from_payload({**state.common, "entity_name": "api"}),
            "relation_id": None,
        }
    )
    store(state, raw(state.edge))
    changed = raw(state.edge)
    changed["edges"][0]["source"]["context"] = {"value": 1.0}
    changed["edges"][0]["relation_id"] = None
    from cyberbrain.core.errors import ConflictError

    with pytest.raises(ConflictError, match="context changed"):
        store(state, changed, context={"value": 1.0})


def test_historical_evidence_cache_cannot_admit_hidden_evidence_to_an_accepted_edge():
    state = setup()
    hidden = state.evolution.store(
        content="Historical-only evidence.",
        entity_name="historical",
        ordinary_recall=False,
        **state.common,
    ).record
    edges = []
    for kind in ("depends_on", "supports"):
        value = state.edge.model_dump(mode="json")
        value.update(kind=kind, relation_id=None)
        value["evidence"] = [{"record_type": "knowledge", "id": str(hidden.id)}]
        edges.append(RelationEdge.model_validate(value))
    edges.sort(key=lambda edge: edge.relation_id)
    bundle = {
        "schema_version": 1,
        "edges": [
            {
                **edges[0].model_dump(mode="json"),
                "status": "rejected",
                "review_note": "Historical.",
            },
            {
                **edges[1].model_dump(mode="json"),
                "status": "accepted",
                "review_note": "Explicit claim.",
            },
        ],
    }
    with bind_authority(owner()), pytest.raises(ConfigurationError, match="unavailable"):
        store(state, bundle)


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", str(UUID(int=9999))),
        ("confidence", 2.0),
        ("schema_version", 999),
    ],
)
def test_malformed_canonical_evidence_is_not_accepted_as_proof(field, value):
    state = setup()
    state.repo.points[state.target.id]["payload"][field] = value
    with pytest.raises(ConfigurationError, match="unavailable"):
        store(state, raw(state.edge))
    assert len(state.repo.points) == 1
