# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from copy import deepcopy
from uuid import UUID

import pytest

from cyberbrain.core.errors import ConfigurationError, StorageError
from cyberbrain.core.settings import Settings
from cyberbrain.knowledge.search import KnowledgeSearchService
from cyberbrain.retrieval.runtime import KnowledgeRetrievalPolicy
from cyberbrain.tenancy import bind_authority
from tests.tenancy.test_runtime_enforcement import authority, matches
from tests.test_services import FakeEmbedding, FakeRepository


class Repository(FakeRepository):
    def __init__(self):
        super().__init__()
        self.filters = []
        self.semantic_ids = []
        self.retire_on_recheck = None

    def _rows(self, query):
        selected = next(
            (c["has_id"] for c in query.get("must", []) if "has_id" in c), None,
        )
        return [
            deepcopy(point) for point in self.points.values()
            if matches(point["payload"], query)
            and (selected is None or point["id"] in selected)
        ]

    def search(self, collection, *, vector, limit, qdrant_filter=None, score_threshold=None):
        self.filters.append(deepcopy(qdrant_filter))
        eligible = {p["id"]: p for p in self._rows(qdrant_filter or {})}
        return [
            {**eligible[point_id], "score": 0.9}
            for point_id in self.semantic_ids if point_id in eligible
        ][:limit]

    def scroll(self, collection, *, qdrant_filter=None, limit=100):
        self.filters.append(deepcopy(qdrant_filter))
        if any("has_id" in c for c in (qdrant_filter or {}).get("must", [])):
            if self.retire_on_recheck:
                self.points[self.retire_on_recheck]["payload"]["status"] = "superseded"
        return self._rows(qdrant_filter or {})[:limit]


def add(repo, index, content, **metadata):
    point_id = UUID(int=index)
    repo.upsert(
        "knowledge", point_id=point_id, vector=[0.1, 0.2, 0.3],
        payload={"status": "active", "content": content, **metadata},
    )
    return str(point_id)


def service(repo, mode="hybrid", **policy):
    return KnowledgeSearchService(
        repository=repo, embedding=FakeEmbedding(), collection="knowledge",
        retrieval_policy=KnowledgeRetrievalPolicy(mode=mode, **policy),
    )


@pytest.mark.parametrize("mode", ["hybrid", "literal"])
def test_lexical_recovers_missing_fingerprint_without_faking_cosine(mode):
    repo = Repository()
    semantic = add(repo, 1, "general release guidance")
    exact = add(repo, 2, "release commit abc1234")
    repo.semantic_ids = [semantic]
    rows = service(repo, mode).search(query="commit abc1234", limit=2)
    assert {row["id"] for row in rows} == {semantic, exact}
    recovered = next(row for row in rows if row["id"] == exact)
    assert recovered["score"] is None
    assert recovered["_retrieval"]["lexical_score"] > 0
    assert next(row for row in rows if row["id"] == semantic)["score"] == 0.9


@pytest.mark.parametrize("mode", ["hybrid", "literal"])
def test_all_identity_filters_apply_in_storage_before_bm25_and_projection(mode):
    repo = Repository()
    identity = dict(tenant="t", user="u", agent="a", project="p", session_id="s")
    allowed = add(repo, 1, "commit abc1234", **identity)
    for index, field in enumerate(identity, 2):
        add(repo, index, "commit abc1234 " * 50, **{**identity, field: "foreign"})
    add(repo, 20, "commit abc1234", **identity, ordinary_recall=False)
    add(repo, 21, "commit abc1234", **identity, record_class="self_model_hypothesis")
    add(repo, 22, "commit abc1234", **identity, status="superseded")
    with bind_authority(authority(tenant="t", user="u", agent="a", project="p", session="s")):
        rows = service(repo, mode).search(query="commit abc1234")
    assert [row["id"] for row in rows] == [allowed]
    for query_filter in repo.filters:
        fields = {c["key"] for c in query_filter["must"] if "key" in c}
        assert set(identity).issubset(fields)
    # The first lexical scan uses exactly the semantic filter, with no global cache.
    assert repo.filters[0] == repo.filters[1]


def test_ranking_is_independent_of_other_tenants_and_no_cross_request_cache():
    repo = Repository()
    first = add(repo, 1, "commit abc1234", tenant="first")
    second = add(repo, 2, "commit abc1234 " * 20, tenant="second")
    search = service(repo)
    with bind_authority(authority(tenant="first")):
        before = search.search(query="commit abc1234")
    with bind_authority(authority(tenant="second")):
        assert [r["id"] for r in search.search(query="commit abc1234")] == [second]
    add(repo, 3, "commit abc1234 " * 200, tenant="second")
    with bind_authority(authority(tenant="first")):
        after = search.search(query="commit abc1234")
    assert before == after
    assert before[0]["id"] == first


@pytest.mark.parametrize("mode", ["hybrid", "literal"])
def test_deleted_or_superseded_candidate_cannot_reenter_from_lexical_scan(mode):
    repo = Repository()
    add(repo, 1, "commit abc1234")
    repo.retire_on_recheck = UUID(int=1)
    assert service(repo, mode).search(query="commit abc1234") == []


@pytest.mark.parametrize("mode", ["vector", "literal"])
def test_vector_default_and_nonliteral_route_do_not_scan_or_change_result(mode):
    repo = Repository()
    point_id = add(repo, 1, "general semantic guidance")
    repo.semantic_ids = [point_id]
    rows = service(repo, mode).search(query="how do I recover from a failed deployment")
    assert rows == [{
        "id": point_id, "score": 0.9, "status": "active",
        "content": "general semantic guidance",
    }]
    assert len(repo.filters) == 1


def test_zero_overlap_never_turns_arbitrary_lexical_rows_into_evidence():
    repo = Repository()
    semantic = add(repo, 1, "semantic evidence")
    add(repo, 2, "unrelated filler")
    repo.semantic_ids = [semantic]
    rows = service(repo).search(query="different terminology")
    assert [row["id"] for row in rows] == [semantic]


def test_bounded_corpus_overflow_is_explicit_not_partial_ranking():
    repo = Repository()
    add(repo, 1, "commit abc1234")
    add(repo, 2, "commit abc1234")
    with pytest.raises(StorageError, match="exceeds configured"):
        service(repo, max_records=1).search(query="commit abc1234")


def test_embedding_or_storage_failure_is_not_disguised_as_empty_or_lexical_success():
    repo = Repository()
    add(repo, 1, "commit abc1234")
    def fail(*args, **kwargs):
        raise StorageError("unavailable")
    repo.search = fail
    with pytest.raises(StorageError):
        service(repo).search(query="commit abc1234")
    assert repo.filters == []


def test_denied_operation_never_embeds_or_scans():
    repo = Repository()
    with bind_authority(authority(project="allowed")):
        with pytest.raises(ConfigurationError):
            service(repo).search(query="commit abc1234", project="foreign")
    assert repo.filters == []


def test_rrf_prefers_agreement_and_is_deterministic():
    repo = Repository()
    vector_first = add(repo, 1, "generic guidance")
    agreement = add(repo, 2, "commit abc1234")
    add(repo, 3, "unrelated filler")
    repo.semantic_ids = [vector_first, agreement]
    search = service(repo)
    rows = search.search(query="commit abc1234", limit=2)
    assert rows[0]["id"] == agreement
    assert rows[0]["_retrieval"]["ranking_score"] > rows[1]["_retrieval"]["ranking_score"]
    assert rows == search.search(query="commit abc1234", limit=2)


@pytest.mark.parametrize("values", [
    {"knowledge_retrieval_mode": "unknown"},
    {"knowledge_retrieval_max_records": 0},
    {"knowledge_retrieval_max_records": 50_001},
    {"knowledge_retrieval_candidate_multiplier": 0},
    {"knowledge_retrieval_candidate_multiplier": 11},
])
def test_invalid_runtime_policy_fails_closed(values):
    with pytest.raises(ConfigurationError):
        Settings(require_auth=False, **values).validate_runtime()


def test_settings_can_select_foreground_hybrid_without_changing_default():
    assert Settings().knowledge_retrieval_mode == "vector"
    Settings(require_auth=False, knowledge_retrieval_mode="hybrid").validate_runtime()


def test_mcp_compact_recall_exposes_lexical_evidence_with_ranking_metadata(monkeypatch):
    import asyncio
    import json
    from types import SimpleNamespace

    import cyberbrain.mcp.server as server
    repo = Repository()
    inside = add(repo, 1, "commit abc1234", tenant="t")
    add(repo, 2, "commit abc1234 " * 20, tenant="foreign")
    monkeypatch.setattr(server, "_runtime", SimpleNamespace(knowledge_search=service(repo)))
    with bind_authority(authority(tenant="t")):
        result = asyncio.run(server.call_tool("knowledge_search", {"query": "commit abc1234"}))
    rows = json.loads(result[0].text)
    assert [row["id"] for row in rows] == [inside]
    assert rows[0]["recall_text"] == "commit abc1234"
    assert "content" not in rows[0]
    assert rows[0]["score"] is None
    assert rows[0]["_retrieval"]["method"] == "hybrid"
