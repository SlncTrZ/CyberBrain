# SPDX-License-Identifier: MPL-2.0
import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from cyberbrain.core.errors import ConfigurationError, ConflictError
from cyberbrain.core.token_budget import DeterministicTokenCounter
from cyberbrain.dreaming.planner import TemporalBucket
from cyberbrain.dreaming.reasoner import EvidenceItem
from cyberbrain.knowledge.evolution import KnowledgeEvolutionService
from cyberbrain.mcp import server as provider
from cyberbrain.relations.dream import DreamRelationRecall
from cyberbrain.relations.models import EntityRef, RelationBundle, RelationEdge, RelationStatus
from cyberbrain.relations.recall import RelationRecallRequest, RelationRecallService
from cyberbrain.relations.review import RelationReviewService
from cyberbrain.relations.storage import RelationIndex
from cyberbrain.relations.traversal import RelationTraversal, TraversalPolicy
from cyberbrain.tenancy import OperationClass, bind_authority
from tests.relations.test_persistence import owner, raw
from tests.relations.test_traversal import PagedRepository, ready
from tests.tenancy.test_runtime_enforcement import CountingEmbedding, authority


def test_caller_context_contains_complete_typed_proof_sets_and_keeps_scores_separate():
    _, records, _, traversal = ready()
    service = RelationRecallService(traversal)
    with bind_authority(owner()):
        result = service.recall(RelationRecallRequest(seed_ids=(records["a"].id,)))
    assert len(result["paths"]) == 4
    assert result["storage_calls"] == 7
    assert result["estimated_tokens"] <= 4096
    assert all("score" not in record for record in result["records"].values())
    for path in result["paths"]:
        assert all("knowledge:" + point_id in result["records"] for point_id in path["record_ids"])
        for step in path["steps"]:
            assert all(
                proof["record_type"] + ":" + proof["id"] in result["records"]
                for proof in step["evidence"]
            )


@pytest.mark.parametrize("budget", [512, 1024, 2048])
def test_context_budget_counts_path_metadata_and_proof_text(budget):
    _, records, _, traversal = ready()
    service = RelationRecallService(traversal)
    with bind_authority(owner()):
        result = service.recall(
            RelationRecallRequest(seed_ids=(records["a"].id,), context_tokens=budget)
        )
    assert result["estimated_tokens"] <= budget
    assert (
        DeterministicTokenCounter().estimate_tokens(json.dumps(result, ensure_ascii=False))
        <= budget
    )
    if len(result["paths"]) < 4:
        assert "context_tokens" in result["truncation_reasons"]


def test_no_paths_without_complete_hydration_on_storage_budget():
    _, records, _, traversal = ready()
    with bind_authority(owner()):
        result = RelationRecallService(traversal).recall(
            RelationRecallRequest(
                seed_ids=(records["a"].id,), policy=TraversalPolicy(max_storage_calls=6)
            )
        )
    assert result["paths"] == [] and result["records"] == {}
    assert result["storage_calls"] == 6
    assert "storage_calls" in result["truncation_reasons"]


def review_fixture():
    repo = PagedRepository()
    evolution = KnowledgeEvolutionService(
        repository=repo,
        embedding=CountingEmbedding(),
        collection="knowledge",
        episodic_collection="episode",
    )
    common = dict(
        domain="qa",
        topic="relations",
        entity_type="component",
        tenant="t",
        user="u",
        agent="a",
        project="p",
    )
    target = evolution.store(content="Database", entity_name="database", **common).record
    source = evolution.store(content="API", entity_name="api", **common).record
    edge = RelationEdge(
        kind="depends_on",
        source=EntityRef.from_payload(source.model_dump(mode="json")),
        target=EntityRef.from_payload(target.model_dump(mode="json")),
        target_record_id=target.id,
        evidence=({"record_type": "knowledge", "id": target.id},),
        valid_from=datetime(2020, 1, 1, tzinfo=UTC),
    )
    index = RelationIndex(repo, "knowledge", "episode")
    return repo, evolution, common, source, edge, RelationReviewService(index, evolution)


def test_proposal_stays_proposed_and_review_versions_native_knowledge():
    repo, _, _, source, edge, service = review_fixture()
    bundle = RelationBundle(schema_version=1, edges=(edge,))
    with bind_authority(owner()):
        proposed = service.propose(source.id, bundle).record
        assert proposed.version == 2
        assert proposed.content == source.content
        assert proposed.extensions["relations"]["edges"][0]["status"] == "proposed"
        accepted = service.review(
            proposed.id, edge.relation_id, RelationStatus.ACCEPTED, "Reviewed canonical evidence."
        ).record
        assert accepted.version == 3
        assert accepted.extensions["relations"]["edges"][0]["status"] == "accepted"
    assert repo.points[source.id]["payload"]["status"] == "superseded"


def test_author_can_propose_but_cannot_accept_or_fake_reviewed_proposal():
    _, _, _, source, edge, service = review_fixture()
    caller = authority(
        tenant="t",
        user="u",
        agent="a",
        project="p",
        operations={OperationClass.READ, OperationClass.WRITE},
    )
    with bind_authority(caller):
        proposed = service.propose(
            source.id, RelationBundle(schema_version=1, edges=(edge,))
        ).record
        with pytest.raises(ConfigurationError, match="admin_review"):
            service.review(proposed.id, edge.relation_id, RelationStatus.ACCEPTED, "Review.")
        accepted = RelationBundle.model_validate(
            raw(edge, status="accepted", review_note="Fake review.")
        )
        with pytest.raises(ConfigurationError, match="only proposed"):
            service.propose(proposed.id, accepted)


def test_concurrent_source_edit_cannot_be_overwritten_by_review():
    _, evolution, common, source, edge, service = review_fixture()
    original = evolution.store

    def concurrent(**values):
        original(content="Concurrent source edit", entity_name="api", **common)
        return original(**values)

    evolution.store = concurrent
    with bind_authority(owner()), pytest.raises(ConflictError, match="source version changed"):
        service.propose(source.id, RelationBundle(schema_version=1, edges=(edge,)))


def test_relation_proposal_cannot_replace_existing_assertion():
    _, _, _, source, edge, service = review_fixture()
    with bind_authority(owner()):
        proposed = service.propose(
            source.id, RelationBundle(schema_version=1, edges=(edge,))
        ).record
        replacement = RelationEdge.model_validate(
            {**edge.model_dump(mode="json"), "valid_until": "2025-01-01T00:00:00Z"}
        )
        with pytest.raises(ConflictError, match="replace"):
            service.propose(proposed.id, RelationBundle(schema_version=1, edges=(replacement,)))


def test_dream_uses_background_scope_and_preserves_historical_provenance():
    repo, records, _, _ = ready()
    index = RelationIndex(repo, "knowledge", "episode", background=True)
    index.verify_indexes()
    adapter = DreamRelationRecall(RelationRecallService(RelationTraversal(index)))
    seed = EvidenceItem(
        id=str(records["a"].id),
        record_type="knowledge",
        content="API",
        score=0.9,
        event_time=datetime(2020, 1, 1, tzinfo=UTC),
        metadata=dict(tenant="t", user="u", agent="a", project="p"),
    )
    background = authority(
        tenant="t",
        user="u",
        agent="a",
        project="p",
        operations={OperationClass.BACKGROUND_REASONING},
    )
    with bind_authority(background):
        expanded = adapter.expand(
            seed=[seed], bucket=TemporalBucket("past", None, datetime(2021, 1, 1, tzinfo=UTC))
        )
    assert len(expanded) == 3
    assert all(item.score is None and item.metadata["relation_paths"] for item in expanded)
    assert all(item.event_time <= datetime(2021, 1, 1, tzinfo=UTC) for item in expanded)
    with bind_authority(
        authority(tenant="t", user="u", agent="a", project="p", operations={OperationClass.READ})
    ):
        with pytest.raises(ConfigurationError):
            adapter.expand(seed=[seed], bucket=TemporalBucket("past", None, datetime.now(UTC)))


def test_mcp_explicit_recall_catalog_dispatch_and_disable_gate():
    _, records, _, traversal = ready()
    previous = provider._runtime
    try:
        provider.configure_runtime(
            SimpleNamespace(relation_recall=RelationRecallService(traversal))
        )
        with bind_authority(owner()):
            response = asyncio.run(
                provider.call_tool("knowledge_relations", {"seed_ids": [str(records["a"].id)]})
            )
            assert json.loads(response[0].text)["returned_path_count"] == 4
            provider.configure_runtime(SimpleNamespace(relation_recall=None))
            response = asyncio.run(
                provider.call_tool("knowledge_relations", {"seed_ids": [str(records["a"].id)]})
            )
            assert "not enabled" in response[0].text
        tools = asyncio.run(provider.list_tools())
        names = {tool.name for tool in tools}
        assert {
            "knowledge_relations",
            "knowledge_relation_propose",
            "knowledge_relation_review",
        } <= names
        import jsonschema

        schema = next(tool.inputSchema for tool in tools if tool.name == "knowledge_relations")
        jsonschema.validate(
            {"seed_ids": [str(records["a"].id)], "policy": {"direction": "in"}}, schema
        )
    finally:
        provider._runtime = previous


def test_mcp_relation_recall_charges_node_budget_and_denies_review_without_write():
    calls = []
    limiter = SimpleNamespace(reserve=lambda caller, charges: calls.append(charges))
    repo, evolution, _, source, edge, review = review_fixture()
    previous = provider._runtime
    try:
        provider.configure_runtime(SimpleNamespace(relation_review=review, quota_limiter=limiter))
        with bind_authority(owner()):
            response = asyncio.run(
                provider.call_tool(
                    "knowledge_relation_propose", {"source_id": str(source.id), "bundle": raw(edge)}
                )
            )
        assert json.loads(response[0].text)["record"]["version"] == 2
        from cyberbrain.tenancy.quota import QuotaResource

        assert calls[0][QuotaResource.WRITES] == 1
        provider.configure_runtime(SimpleNamespace(relation_recall=None, quota_limiter=limiter))
        with bind_authority(owner()):
            asyncio.run(
                provider.call_tool(
                    "knowledge_relations",
                    {"seed_ids": [str(source.id)], "policy": {"max_nodes": 12}},
                )
            )
        assert calls[-1][QuotaResource.RECALL_LIMIT] == 12
    finally:
        provider._runtime = previous


def test_dream_engine_wires_relation_expansion_after_direct_topic_eligibility():
    from cyberbrain.dreaming.engine import DreamingEngine
    from cyberbrain.dreaming.planner import DreamPlan, EpisodeSnippet

    repo, records, _, _ = ready()
    index = RelationIndex(repo, "knowledge", "episode", background=True)
    index.verify_indexes()
    seed = EvidenceItem(
        id=str(records["a"].id),
        record_type="knowledge",
        content="API dependency anchor",
        score=0.9,
        event_time=datetime(2020, 1, 1, tzinfo=UTC),
        metadata=dict(tenant="t", user="u", agent="a", project="p"),
    )
    bucket = TemporalBucket("past", None, datetime(2021, 1, 1, tzinfo=UTC))
    planner = SimpleNamespace(
        plan=lambda *args, **kwargs: DreamPlan(
            ["API dependencies"], [bucket], bucket.end, bucket.end
        )
    )
    engine = DreamingEngine(
        retriever=SimpleNamespace(recall=lambda **kwargs: [seed]),
        reasoner=None,
        planner=planner,
        relation_expander=DreamRelationRecall(RelationRecallService(RelationTraversal(index))),
    )
    with bind_authority(owner()):
        request = engine.prepare_request(
            [EpisodeSnippet("API dependencies", bucket.end, "p")], session_id="completed-session"
        )
    related = [
        item
        for item in request.evidence_by_topic["API dependencies"]
        if item.metadata.get("relation_paths")
    ]
    assert related
    assert all(item.score is None for item in related)


def test_dream_path_and_proof_metadata_fit_the_actual_serialized_budget():
    from dataclasses import asdict

    repo, records, _, _ = ready()
    index = RelationIndex(repo, "knowledge", "episode", background=True)
    index.verify_indexes()
    adapter = DreamRelationRecall(
        RelationRecallService(RelationTraversal(index)), total_limit=1, context_tokens=2048
    )
    seed = EvidenceItem(
        id=str(records["a"].id),
        record_type="knowledge",
        content="anchor",
        score=0.9,
        event_time=datetime(2020, 1, 1, tzinfo=UTC),
        metadata=dict(tenant="t", user="u", agent="a", project="p"),
    )
    with bind_authority(owner()):
        expanded = adapter.expand(
            seed=[seed], bucket=TemporalBucket("past", None, datetime(2021, 1, 1, tzinfo=UTC))
        )
    assert len(expanded) == 1
    assert all(len(path["steps"]) == 1 for path in expanded[0].metadata["relation_paths"])
    tokens = DeterministicTokenCounter().estimate_tokens(
        json.dumps([asdict(item) for item in expanded], ensure_ascii=False, default=str)
    )
    assert tokens <= 2048


def test_compact_recall_keeps_small_relation_summary_and_exact_view_keeps_assertions():
    repo, records, _, _ = ready()
    source = repo.points[records["a"].id]["payload"]
    compact = provider._project_recall_rows([source], view="compact")[0]
    assert "relations" not in compact["extensions"]
    assert "_relation_index" not in compact["extensions"]
    assert compact["relation_summary"]["accepted"] == 2
    assert source["extensions"]["relations"]["edges"]
    assert provider._project_recall_rows([source], view="full")[0] == source


def test_scoped_admin_can_select_one_authorized_source_from_a_multi_user_grant():
    _, _, _, source, edge, service = review_fixture()
    caller = authority(tenant="t", user=["u", "v"], agent="a", project="p")
    with bind_authority(caller):
        proposed = service.propose(
            source.id, RelationBundle(schema_version=1, edges=(edge,))
        ).record
        accepted = service.review(
            proposed.id, edge.relation_id, RelationStatus.ACCEPTED, "Authorized scoped review."
        ).record
    assert accepted.user == "u"


def test_review_requires_write_authority_before_source_read():
    repo, _, _, source, edge, service = review_fixture()
    caller = authority(
        tenant="t",
        user="u",
        agent="a",
        project="p",
        operations={OperationClass.READ, OperationClass.ADMIN_REVIEW},
    )
    repo.calls.clear()
    with bind_authority(caller), pytest.raises(ConfigurationError, match="write authority"):
        service.review(source.id, edge.relation_id, RelationStatus.ACCEPTED, "Review.")
    assert repo.calls == []
