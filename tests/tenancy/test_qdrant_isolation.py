# SPDX-License-Identifier: MPL-2.0
"""Optional storage-boundary gate; requires a new empty loopback-only Qdrant."""

import os
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
import pytest

from cyberbrain.dreaming.session import QdrantSessionEpisodeLoader
from cyberbrain.knowledge.evolution import KnowledgeEvolutionService
from cyberbrain.knowledge.search import KnowledgeSearchService
from cyberbrain.memory.service import MemoryService
from cyberbrain.retrieval.runtime import KnowledgeRetrievalPolicy
from cyberbrain.schemas.models import DreamStatus
from cyberbrain.storage.qdrant import QdrantRepository
from cyberbrain.tenancy import (
    DeploymentMode,
    IdentityScope,
    OperationClass,
    authority_for_authenticated_scope,
    bind_authority,
)
from tests.tenancy.test_runtime_enforcement import CountingEmbedding


@pytest.mark.skipif(
    not os.environ.get("CYBERBRAIN_QA_QDRANT_URL"),
    reason="isolated empty Qdrant QA endpoint required",
)
def test_real_qdrant_isolates_versions_exact_reads_and_session_updates(tmp_path):
    url = os.environ["CYBERBRAIN_QA_QDRANT_URL"]
    parsed = urlsplit(url)
    assert parsed.hostname in {"127.0.0.1", "localhost"}
    assert parsed.port is not None and not parsed.username and not parsed.password
    headers = {"api-key": os.environ.get("CYBERBRAIN_QA_QDRANT_KEY", "")}
    response = httpx.get(url + "/collections", headers=headers)
    response.raise_for_status()
    assert response.json()["result"]["collections"] == [], "QA requires a new empty instance"
    repo = QdrantRepository(base_url=url, api_key=headers["api-key"])
    embedding = CountingEmbedding()
    for name in ("cyberbrain_knowledge", "cyberbrain_episodic"):
        repo.ensure_collection(name, vector_size=embedding.dimension)
    memory = MemoryService(
        repository=repo,
        embedding=embedding,
        collection="cyberbrain_episodic",
        score_threshold=None,
    )
    evolution = KnowledgeEvolutionService(
        repository=repo,
        embedding=embedding,
        collection="cyberbrain_knowledge",
    )
    authorities = {
        name: authority_for_authenticated_scope(
            DeploymentMode.MULTI_USER,
            scope=IdentityScope.from_values(
                tenant=name, user="same", agent="shared", project="same"
            ),
            operations=frozenset(OperationClass),
        )
        for name in ("one", "two")
    }
    memories = {}
    knowledge = {}
    common = dict(domain="qa", topic="isolation", entity_type="policy", entity_name="same")
    for name, caller in authorities.items():
        with bind_authority(caller):
            memories[name] = memory.store(
                content="experience " + name,
                session_id="same-session",
                event_time=datetime.now(UTC),
            )
            knowledge[name] = evolution.store(content="policy " + name, **common)
    assert knowledge["one"].record.version == knowledge["two"].record.version == 1
    with bind_authority(authorities["one"]):
        rows = memory.search(query="experience", limit=10)
        assert [row["tenant"] for row in rows] == ["one"]
        assert memory.get(point_id=memories["two"].id, authority=authorities["one"]) is None
        revised = evolution.store(content="revised policy one", **common)
        assert revised.record.version == 2
        assert revised.previous_id == knowledge["one"].record.id
        loader = QdrantSessionEpisodeLoader(repository=repo, collection="cyberbrain_episodic")
        assert loader.update_status("same-session", status=DreamStatus.PROCESSED) == 1
    foreign = memory.get(point_id=memories["two"].id, authority=authorities["two"])
    assert foreign["dream_status"] == "pending"
    untouched = repo.retrieve("cyberbrain_knowledge", point_id=knowledge["two"].record.id)
    assert untouched["payload"]["status"] == "active"
    assert untouched["payload"]["content"] == "policy two"

    # Exercise BM25 recovery and has_id revalidation against real Qdrant.
    from uuid import UUID

    fingerprint_id = UUID(int=1000)
    repo.upsert(
        "cyberbrain_knowledge",
        point_id=fingerprint_id,
        vector=[-value for value in embedding.embed("opposite")],
        payload={
            "content": "commit abc1234",
            "status": "active",
            "record_class": "knowledge",
            "ordinary_recall": True,
            "tenant": "one",
            "user": "same",
            "agent": "shared",
            "project": "same",
        },
    )
    repo.upsert(
        "cyberbrain_knowledge",
        point_id=UUID(int=1001),
        vector=[-value for value in embedding.embed("opposite")],
        payload={
            "content": "commit abc1234 " * 30,
            "status": "active",
            "tenant": "two",
            "user": "same",
            "agent": "shared",
            "project": "same",
        },
    )
    for mode in ("hybrid", "literal"):
        search = KnowledgeSearchService(
            repository=repo,
            embedding=embedding,
            collection="cyberbrain_knowledge",
            score_threshold=0.55,
            retrieval_policy=KnowledgeRetrievalPolicy(mode=mode),
        )
        with bind_authority(authorities["one"]):
            rows = search.search(query="commit abc1234", limit=10)
        assert all(row["tenant"] == "one" and row["status"] == "active" for row in rows)
        recovered = next(row for row in rows if row["id"] == str(fingerprint_id))
        assert recovered["score"] is None
        assert recovered["_retrieval"]["lexical_score"] > 0

    # Typed assertions use the same scoped get boundary and native Evolution.
    from cyberbrain.relations import EntityRef, EvidenceRef, RelationBundle, RelationEdge

    with bind_authority(authorities["one"]):
        target_record = evolution.store(
            content="Dependency target.",
            **{**common, "entity_name": "dependency"},
        ).record
        relation = RelationEdge(
            kind="depends_on",
            source=EntityRef.from_payload(revised.record.model_dump(mode="json")),
            target=EntityRef.from_payload(target_record.model_dump(mode="json")),
            target_record_id=target_record.id,
            evidence=(EvidenceRef(record_type="knowledge", id=target_record.id),),
            status="accepted",
            review_note="Explicit fixture review.",
            valid_from=datetime(2026, 10, 1, tzinfo=UTC),
        )
        bundle = RelationBundle(schema_version=1, edges=(relation,)).model_dump(mode="json")
        linked = evolution.store(
            content=revised.record.content,
            **common,
            extensions={"relations": bundle},
        )
        retry = evolution.store(
            content=revised.record.content,
            **common,
            extensions={"relations": bundle},
        )
        assert linked.record.version == revised.record.version + 1
        assert linked.record.content_hash == revised.record.content_hash
        assert retry.record.id == linked.record.id
        persisted = repo.retrieve(
            "cyberbrain_knowledge",
            linked.record.id,
            qdrant_filter={"must": [{"key": "tenant", "match": {"value": "one"}}]},
        )
        assert persisted["payload"]["extensions"]["relations"] == bundle
        foreign_evidence = {
            **bundle,
            "edges": [
                {
                    **bundle["edges"][0],
                    "evidence": [
                        {"record_type": "knowledge", "id": str(knowledge["two"].record.id)},
                    ],
                },
            ],
        }
        from cyberbrain.core.errors import ConfigurationError

        with pytest.raises(ConfigurationError, match="endpoint or evidence unavailable"):
            evolution.store(
                content=revised.record.content,
                **common,
                extensions={"relations": foreign_evidence},
            )
        assert (
            repo.retrieve("cyberbrain_knowledge", linked.record.id)["payload"]["status"] == "active"
        )

    # Indexed traversal uses the same two collections and a separate fixture scope.
    from cyberbrain.relations.storage import RelationIndex
    from cyberbrain.relations.traversal import RelationTraversal, TraversalPolicy
    from tests.relations.test_traversal import check_diamond, graph

    graph_scope = dict(tenant="graph", user="same", agent="shared", project="same")
    graph_caller = authority_for_authenticated_scope(
        DeploymentMode.MULTI_USER,
        scope=IdentityScope.from_values(**graph_scope),
        operations=frozenset(OperationClass),
    )
    fixtures = graph(repo, "cyberbrain_knowledge", graph_scope)
    index = RelationIndex(repo, "cyberbrain_knowledge", "cyberbrain_episodic")
    with bind_authority(graph_caller):
        index.prepare_indexes()
        index.verify_indexes()
        engine = RelationTraversal(index)
        check_diamond(engine, fixtures)
        historical = engine.traverse(
            [fixtures["a"].id], TraversalPolicy(as_of=datetime(2021, 1, 1, tzinfo=UTC))
        )
        assert len(historical["paths"]) == 4
        assert historical["storage_calls"] == 6
        with pytest.raises(ConfigurationError, match="seed unavailable"):
            engine.traverse([linked.record.id])
    collections = httpx.get(url + "/collections", headers=headers).json()["result"]["collections"]
    assert len(collections) == 2

    # Caller packing and proposal/review execute against real storage.
    from cyberbrain.backup.service import BackupService, QdrantSnapshotClient
    from cyberbrain.relations.maintenance import RelationMaintenance
    from cyberbrain.relations.models import RelationStatus
    from cyberbrain.relations.recall import RelationRecallRequest, RelationRecallService
    from cyberbrain.relations.review import RelationReviewService

    with bind_authority(graph_caller):
        review = RelationReviewService(index, evolution)
        proposed_edge = RelationEdge(
            kind="supports",
            source=EntityRef.from_payload(fixtures["a"].model_dump(mode="json")),
            target=EntityRef.from_payload(fixtures["d"].model_dump(mode="json")),
            target_record_id=fixtures["d"].id,
            evidence=(EvidenceRef(record_type="knowledge", id=fixtures["d"].id),),
            valid_from=datetime(2020, 1, 1, tzinfo=UTC),
        )
        proposal = review.propose(
            fixtures["a"].id, RelationBundle(schema_version=1, edges=(proposed_edge,))
        ).record
        reviewed = review.review(
            proposal.id,
            proposed_edge.relation_id,
            RelationStatus.ACCEPTED,
            "Explicit controlled fixture review.",
        ).record
        recalled = RelationRecallService(engine).recall(
            RelationRecallRequest(
                seed_ids=(reviewed.id,), policy=TraversalPolicy(depth=1, kinds={"supports"})
            )
        )
        assert recalled["returned_path_count"] == 1
        assert recalled["storage_calls"] == 5
        assert recalled["estimated_tokens"] <= recalled["context_budget"]

        # Exercise a protected pre-backfill snapshot and real snapshot rollback.
        scoped = repo.scroll(
            "cyberbrain_knowledge",
            qdrant_filter={"must": [{"key": "tenant", "match": {"value": "graph"}}]},
            limit=100,
        )
        ids = [point["id"] for point in scoped]
        before = repo._request(
            "POST",
            "/collections/cyberbrain_knowledge/points",
            json={"ids": ids, "with_payload": True, "with_vector": True},
        )["result"]
        for point in scoped:
            extensions = dict(point["payload"]["extensions"])
            extensions.pop("_relation_index")
            repo.set_payload(
                "cyberbrain_knowledge",
                point_id=UUID(point["id"]),
                payload={"extensions": extensions},
            )
        maintenance = RelationMaintenance(index)
        snapshots = QdrantSnapshotClient(base_url=url)
        checkpoint = tmp_path / "relation-checkpoint"
        census = maintenance.checkpoint(
            destination=checkpoint, snapshots=snapshots, writers_quiesced=True
        )
        assert census.missing == len(ids)
        applied = maintenance.apply(
            checkpoint=checkpoint, expected_source_hash=census.source_hash, writers_quiesced=True
        )
        assert applied.missing == 0 and applied.source_hash == census.source_hash
        after = repo._request(
            "POST",
            "/collections/cyberbrain_knowledge/points",
            json={"ids": ids, "with_payload": True, "with_vector": True},
        )["result"]
        assert {p["id"]: p["vector"] for p in before} == {p["id"]: p["vector"] for p in after}
        assert {p["id"]: p["payload"] for p in before} == {p["id"]: p["payload"] for p in after}
        BackupService(qdrant=snapshots, collections=[]).restore(
            source=checkpoint, sqlite_destinations={}
        )
        rolled_back = maintenance.census()
        assert rolled_back.missing == census.missing
        assert rolled_back.source_hash == census.source_hash
        assert (
            maintenance.apply(
                checkpoint=checkpoint,
                expected_source_hash=census.source_hash,
                writers_quiesced=True,
            ).missing
            == 0
        )
        assert (
            len(httpx.get(url + "/collections", headers=headers).json()["result"]["collections"])
            == 2
        )

    # Release regression: real-storage retries preserve scoped prospective evidence.
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from cyberbrain.cognition.prediction import PredictionLearningService

    learning = PredictionLearningService(
        memory=memory,
        repository=repo,
        episodic_collection="cyberbrain_episodic",
        process_lock_file=str(tmp_path / "prediction.lock"),
    )
    recorded = {}
    for name, caller in authorities.items():
        with bind_authority(caller):
            recorded[name] = learning.record_prediction(
                expected_outcome=f"prospective result {name}",
                confidence=0.8,
                session_id="prediction-session",
                event_time=datetime.now(UTC),
                correlation_id="same-correlation",
            )
    assert recorded["one"].id != recorded["two"].id
    assert recorded["two"].tenant == "two"
    with bind_authority(authorities["one"]):
        retry = learning.record_prediction(
            expected_outcome="changed retry",
            confidence=0.1,
            session_id="prediction-session",
            event_time=datetime.now(UTC),
            correlation_id="same-correlation",
        )
    assert retry == recorded["one"]

    barrier = Barrier(2)

    def concurrent_prediction(index):
        with bind_authority(authorities["one"]):
            barrier.wait(timeout=10)
            return learning.record_prediction(
                expected_outcome=f"race expectation {index}",
                confidence=0.8,
                session_id="race-session",
                event_time=datetime.now(UTC),
                correlation_id="concurrent-correlation",
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        left, right = list(pool.map(concurrent_prediction, range(2)))
    assert left == right
    point = repo.retrieve("cyberbrain_episodic", left.id)
    assert point["payload"] == left.model_dump(mode="json")
