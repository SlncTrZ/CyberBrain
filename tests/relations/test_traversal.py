# SPDX-License-Identifier: MPL-2.0
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from cyberbrain.core.errors import ConfigurationError, StorageError
from cyberbrain.relations.index import INDEX_FIELDS, INDEX_KEY, project_relations
from cyberbrain.relations.models import EntityRef, EvidenceRef, RelationBundle, RelationEdge
from cyberbrain.relations.storage import RelationIndex, TraversalLimit
from cyberbrain.relations.traversal import RelationTraversal, TraversalPolicy
from cyberbrain.schemas.models import KnowledgeRecord
from cyberbrain.tenancy import OperationClass, bind_authority
from tests.relations.test_persistence import Repository, owner
from tests.tenancy.test_runtime_enforcement import authority


class PagedRepository(Repository):
    def __init__(self):
        super().__init__()
        self.schema = {}
        self.calls = []
        self.fail = False

    @staticmethod
    def match(point, condition):
        if "has_id" in condition:
            return str(point["id"]) in condition["has_id"]
        if "should" in condition:
            return any(PagedRepository.match(point, c) for c in condition["should"])
        if "must" in condition or "must_not" in condition:
            return all(
                PagedRepository.match(point, c) for c in condition.get("must", [])
            ) and not any(PagedRepository.match(point, c) for c in condition.get("must_not", []))
        value = point["payload"]
        key = condition.get("key") or condition["is_empty"]["key"]
        for part in key.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        if "is_empty" in condition:
            return value is None
        if "range" in condition:
            return value is not None and datetime.fromisoformat(value) <= datetime.fromisoformat(
                condition["range"]["lte"]
            )
        match = condition["match"]
        if "value" in match:
            return value == match["value"]
        return (
            any(v in match["any"] for v in value)
            if isinstance(value, list)
            else value in match["any"]
        )

    def scroll_page(self, collection, *, qdrant_filter, limit, offset=None):
        self.calls.append((collection, deepcopy(qdrant_filter), limit))
        if self.fail:
            raise StorageError("injected")
        points = [
            deepcopy(p)
            for key, p in self.points.items()
            if self.collections[key] == collection and self.match(p, qdrant_filter)
        ]
        return points[:limit], ("more" if len(points) > limit else None)

    def collection_info(self, name):
        return {"payload_schema": self.schema}

    def create_payload_index(self, collection, *, field, schema):
        self.schema[field] = {"data_type": schema}

    def set_payload(self, collection, *, point_id, payload):
        return super().set_payload(collection, point_id=UUID(str(point_id)), payload=payload)


def graph(repo, knowledge="knowledge", scope=None):
    scope = scope or dict(tenant="t", user="u", agent="a", project="p")
    records = {
        name: KnowledgeRecord(
            content=name,
            content_hash=name,
            domain="qa",
            topic="graph",
            entity_type="component",
            entity_name=name,
            created_at=datetime(2020, 1, 1, tzinfo=UTC),
            **scope,
        )
        for name in ("a", "b", "c", "d")
    }
    links = {"a": ["b", "c"], "b": ["d"], "c": ["d"], "d": ["a"]}
    for name, record in records.items():
        edges = tuple(
            RelationEdge(
                kind="depends_on",
                source=EntityRef.from_payload(record.model_dump(mode="json")),
                target=EntityRef.from_payload(records[target].model_dump(mode="json")),
                target_record_id=records[target].id,
                evidence=(EvidenceRef(record_type="knowledge", id=records[target].id),),
                status="accepted",
                review_note="Controlled graph fixture.",
                valid_from=datetime(2020, 1, 1, tzinfo=UTC),
            )
            for target in links[name]
        )
        record.extensions["relations"] = RelationBundle(schema_version=1, edges=edges).model_dump(
            mode="json"
        )
        payload = record.model_dump(mode="json")
        payload["extensions"][INDEX_KEY] = project_relations(payload)
        repo.upsert(knowledge, point_id=record.id, vector=[0.1, 0.2, 0.3], payload=payload)
    return records


def ready(repo=None):
    repo = repo or PagedRepository()
    records = graph(repo)
    index = RelationIndex(repo, "knowledge", "episode")
    with bind_authority(owner()):
        index.prepare_indexes()
    return repo, records, index, RelationTraversal(index)


def check_diamond(engine, records):
    result = engine.traverse([records["a"].id])
    assert result["storage_calls"] == 6
    assert result["node_count"] == 4
    paths = [p for p in result["paths"] if p["record_ids"][-1] == str(records["d"].id)]
    assert len(paths) == 2
    assert all(len(p["steps"]) == 2 for p in paths)
    assert paths[0]["record_ids"] != paths[1]["record_ids"]
    assert all(
        step["evidence"] and step["owner_version"] == 1 for path in paths for step in path["steps"]
    )
    reverse = engine.traverse([records["d"].id], TraversalPolicy(direction="in"))
    assert len([p for p in reverse["paths"] if p["record_ids"][-1] == str(records["a"].id)]) == 2


def test_diamond_reverse_cycle_and_provenance():
    _, records, _, engine = ready()
    with bind_authority(owner()):
        check_diamond(engine, records)
        result = engine.traverse([records["a"].id], TraversalPolicy(depth=3))
    assert result["storage_calls"] == 8
    assert all(len(p["node_keys"]) == len(set(p["node_keys"])) for p in result["paths"])
    assert not result["truncated"]


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("max_nodes", 1, "nodes"),
        ("max_edges", 1, "edges"),
        ("max_paths", 1, "paths"),
        ("max_storage_calls", 3, "storage_calls"),
    ],
)
def test_budgets_are_explicit(field, value, reason):
    _, records, _, engine = ready()
    with bind_authority(owner()):
        result = engine.traverse([records["a"].id], TraversalPolicy(**{field: value}))
    assert reason in result["truncation_reasons"]
    assert result["storage_calls"] <= (value if field == "max_storage_calls" else 8)


def test_missing_or_tampered_projection_and_prepare_fail_closed():
    repo, records, index, engine = ready()
    with bind_authority(owner()):
        index._verified = False
        with pytest.raises(ConfigurationError, match="verified"):
            engine.traverse([records["a"].id])
        index.verify_indexes()
        del repo.points[records["b"].id]["payload"]["extensions"][INDEX_KEY]
        with pytest.raises(ConfigurationError, match="rebuild"):
            engine.traverse([records["a"].id])
        assert index.rebuild() == 4
        check_diamond(engine, records)
        repo.points[records["a"].id]["payload"]["extensions"][INDEX_KEY]["target_keys"] = []
        with pytest.raises(ConfigurationError, match="inconsistent"):
            engine.traverse([records["a"].id])


def test_read_and_maintenance_authority_precedes_io():
    repo, records, index, engine = ready()
    repo.calls.clear()
    with pytest.raises(ConfigurationError, match="authority"):
        engine.traverse([records["a"].id])
    with bind_authority(
        authority(tenant="t", user="u", agent="a", project="p", operations={OperationClass.READ})
    ):
        with pytest.raises(ConfigurationError, match="admin_review"):
            index.rebuild()
    assert not repo.calls


def test_foreign_seed_and_hidden_intermediate_cannot_bridge():
    repo, records, _, engine = ready()
    foreign = graph(repo, scope=dict(tenant="foreign", user="u", agent="a", project="p"))
    with bind_authority(owner()):
        with pytest.raises(ConfigurationError, match="unavailable"):
            engine.traverse([foreign["a"].id])
        repo.points[records["b"].id]["payload"]["ordinary_recall"] = False
        repo.points[records["c"].id]["payload"]["ordinary_recall"] = False
        result = engine.traverse([records["a"].id])
    assert result["paths"] == []
    assert all(query["must"][0] for _, query, _ in repo.calls)


def test_target_update_does_not_redirect_and_historical_anchors_remain_explicit():
    repo, records, _, engine = ready()
    old = repo.points[records["b"].id]["payload"]
    old["status"] = "superseded"
    new = deepcopy(old)
    new.update(
        id=str(uuid4()), version=2, status="active", created_at=datetime.now(UTC).isoformat()
    )
    repo.upsert("knowledge", point_id=UUID(new["id"]), vector=[0.1, 0.2, 0.3], payload=new)
    with bind_authority(owner()):
        result = engine.traverse([records["a"].id])
        assert all(str(records["b"].id) not in p["record_ids"] for p in result["paths"])
        historical = engine.traverse(
            [records["a"].id], TraversalPolicy(as_of=datetime(2021, 1, 1, tzinfo=UTC))
        )
        assert any(str(records["b"].id) in p["record_ids"] for p in historical["paths"])
        old["ordinary_recall"] = False
        assert all(
            str(records["b"].id) not in p["record_ids"]
            for p in engine.traverse(
                [records["a"].id], TraversalPolicy(as_of=datetime(2021, 1, 1, tzinfo=UTC))
            )["paths"]
        )


def test_ambiguous_head_and_storage_failure_are_explicit():
    repo, records, _, engine = ready()
    duplicate = deepcopy(repo.points[records["b"].id]["payload"])
    duplicate["id"] = str(uuid4())
    repo.upsert(
        "knowledge", point_id=UUID(duplicate["id"]), vector=[0.1, 0.2, 0.3], payload=duplicate
    )
    with bind_authority(owner()):
        with pytest.raises(ConfigurationError, match="ambiguous"):
            engine.traverse([records["a"].id])
        repo.fail = True
        with pytest.raises(StorageError, match="injected"):
            engine.traverse([records["a"].id])


def test_temporal_interval_proposed_and_kind_filter():
    repo, records, _, engine = ready()
    payload = repo.points[records["a"].id]["payload"]
    edges = payload["extensions"]["relations"]["edges"]
    edges[0]["valid_until"] = datetime(2021, 1, 1, tzinfo=UTC).isoformat()
    edges[1]["status"] = "proposed"
    edges[1]["review_note"] = None
    payload["extensions"][INDEX_KEY] = project_relations(payload)
    with bind_authority(owner()):
        assert engine.traverse([records["a"].id])["paths"] == []
        assert (
            engine.traverse([records["a"].id], TraversalPolicy(kinds={"supports"}))["paths"] == []
        )
        historical = engine.traverse(
            [records["a"].id], TraversalPolicy(as_of=datetime(2020, 6, 1, tzinfo=UTC))
        )
        assert len(historical["paths"]) == 2
        boundary = engine.traverse(
            [records["a"].id], TraversalPolicy(as_of=datetime(2021, 1, 1, tzinfo=UTC))
        )
        assert not boundary["paths"]


def test_fanout_overflow_never_selects_arbitrary_partial_head_or_mutates_rebuild():
    repo, records, index, engine = ready()
    original = repo.scroll_page

    def overflowing(collection, **kwargs):
        points, continuation = original(collection, **kwargs)
        if kwargs["limit"] == 256:
            continuation = "more"
        return points, continuation

    repo.scroll_page = overflowing
    with bind_authority(owner()):
        result = engine.traverse([records["a"].id])
        assert result["paths"] == []
        assert result["truncation_reasons"] == ["candidate_capacity"]
        before = deepcopy(repo.points)
        with pytest.raises(TraversalLimit):
            index.rebuild()
        assert repo.points == before


@pytest.mark.parametrize(
    "kwargs",
    [
        {"depth": True},
        {"depth": 4},
        {"max_storage_calls": 0},
        {"as_of": datetime(2020, 1, 1)},
        {"direction": "sideways"},
    ],
)
def test_invalid_policies(kwargs):
    with pytest.raises(ValueError):
        TraversalPolicy(**kwargs)


def test_contradicts_is_symmetric_without_fabricating_an_inverse_assertion():
    repo, records, _, engine = ready()
    payload = repo.points[records["b"].id]["payload"]
    edge = payload["extensions"]["relations"]["edges"][0]
    edge.update(kind="contradicts", relation_id=None)
    payload["extensions"][INDEX_KEY] = project_relations(payload)
    with bind_authority(owner()):
        result = engine.traverse([records["d"].id], TraversalPolicy(kinds={"contradicts"}))
    assert len(result["paths"]) == 1
    step = result["paths"][0]["steps"][0]
    assert step["direction"] == "in"
    assert step["owner_record_id"] == str(records["b"].id)
    assert step["target_record_id"] == str(records["d"].id)


@pytest.mark.parametrize("change", ["hidden", "future", "foreign", "unknown_schema", "wrong_type"])
def test_episode_proof_is_typed_scoped_and_temporal(change):
    from cyberbrain.schemas.models import EpisodeRecord

    repo, records, _, engine = ready()
    episode = EpisodeRecord(
        content="Observation",
        content_hash="observation",
        session_id="past",
        event_time=datetime(2020, 1, 1, tzinfo=UTC),
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
        tenant="t",
        user="u",
        agent="a",
        project="p",
    )
    proof = episode.model_dump(mode="json")
    repo.upsert("episode", point_id=episode.id, vector=[0.1, 0.2, 0.3], payload=proof)
    payload = repo.points[records["a"].id]["payload"]
    for edge in payload["extensions"]["relations"]["edges"]:
        edge["evidence"] = [{"record_type": "episode", "id": str(episode.id)}]
    payload["extensions"][INDEX_KEY] = project_relations(payload)
    with bind_authority(owner()):
        result = engine.traverse([records["a"].id], TraversalPolicy(depth=1))
        assert len(result["paths"]) == 2 and result["storage_calls"] == 5
        if change == "hidden":
            proof["ordinary_recall"] = False
        elif change == "future":
            proof["event_time"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        elif change == "foreign":
            proof["tenant"] = "other"
        elif change == "unknown_schema":
            proof["schema_version"] = 100
        else:
            proof["record_type"] = "knowledge"
        if change == "unknown_schema":
            with pytest.raises(ConfigurationError, match="unavailable"):
                engine.traverse([records["a"].id])
        else:
            assert engine.traverse([records["a"].id])["paths"] == []


def test_new_owner_withdrawal_does_not_resurrect_historical_edges_in_reverse_lookup():
    repo, records, _, engine = ready()
    old = repo.points[records["b"].id]["payload"]
    old["status"] = "superseded"
    new = deepcopy(old)
    new.update(
        id=str(uuid4()), version=2, status="active", created_at=datetime.now(UTC).isoformat()
    )
    new["extensions"]["relations"] = {"schema_version": 1, "edges": []}
    new["extensions"][INDEX_KEY] = project_relations(new)
    repo.upsert("knowledge", point_id=UUID(new["id"]), vector=[0.1, 0.2, 0.3], payload=new)
    with bind_authority(owner()):
        result = engine.traverse([records["d"].id], TraversalPolicy(direction="in"))
    assert all(str(records["b"].id) not in p["record_ids"] for p in result["paths"])
    assert all(new["id"] not in p["record_ids"] for p in result["paths"])


def test_server_owned_projection_cannot_be_injected_by_knowledge_caller():
    from tests.relations.test_persistence import setup, store

    state = setup()
    with pytest.raises(ConfigurationError, match="server-owned"):
        store(state, extensions={INDEX_KEY: {"schema_version": 1}})


def test_staged_owner_and_wrong_index_schema_are_never_accepted():
    repo, records, index, engine = ready()
    repo.points[records["b"].id]["payload"]["extensions"]["_evolution_state"] = "pending_activation"
    with bind_authority(owner()):
        result = engine.traverse([records["a"].id])
        assert all(str(records["b"].id) not in p["record_ids"] for p in result["paths"])
        repo.schema[next(iter(INDEX_FIELDS))] = {"data_type": "keyword"}
        with pytest.raises(ConfigurationError, match="missing"):
            index.verify_indexes()


def test_qdrant_paged_adapter_makes_one_request_and_preserves_continuation():
    import httpx

    from cyberbrain.storage.qdrant import QdrantRepository

    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "result": {"points": [{"id": "x", "payload": {}}], "next_page_offset": "next"},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        repo = QdrantRepository(base_url="http://qdrant.invalid", client=client)
        points, continuation = repo.scroll_page("knowledge", qdrant_filter={"must": []}, limit=1)
        assert len(calls) == 1 and len(points) == 1 and continuation == "next"
        with pytest.raises(ValueError):
            repo.scroll_page("knowledge", limit=257)
        assert len(calls) == 1


def test_three_hop_chain_reaches_third_target_within_eight_reads():
    repo, records, _, engine = ready()
    for source, target in [("a", "b"), ("b", "c"), ("c", "d")]:
        payload = repo.points[records[source].id]["payload"]
        edge = RelationEdge(
            kind="part_of",
            source=EntityRef.from_payload(payload),
            target=EntityRef.from_payload(records[target].model_dump(mode="json")),
            target_record_id=records[target].id,
            evidence=(EvidenceRef(record_type="knowledge", id=records[target].id),),
            status="accepted",
            review_note="Controlled chain fixture.",
            valid_from=datetime(2020, 1, 1, tzinfo=UTC),
        )
        payload["extensions"]["relations"] = RelationBundle(
            schema_version=1, edges=(edge,)
        ).model_dump(mode="json")
        payload["extensions"][INDEX_KEY] = project_relations(payload)
    with bind_authority(owner()):
        result = engine.traverse([records["a"].id], TraversalPolicy(depth=3, kinds={"part_of"}))
    assert result["storage_calls"] == 8
    assert len(result["paths"][-1]["steps"]) == 3
    assert result["paths"][-1]["record_ids"][-1] == str(records["d"].id)
