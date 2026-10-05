# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from uuid import uuid4

from cyberbrain.retrieval.runtime import KnowledgeRetrievalPolicy, rank_knowledge
from tests.test_dream_writeback import FakeRepository


def test_retrieval_policy_closure_defaults_to_vector() -> None:
    policy = KnowledgeRetrievalPolicy()
    assert policy.mode == "vector"
    assert not policy.uses_lexical("regular query")
    assert not policy.uses_lexical("exact_token_query")


def test_retrieval_policy_literal_opt_in_detects_literal_queries() -> None:
    policy = KnowledgeRetrievalPolicy(mode="literal")
    assert policy.mode == "literal"
    # Ordinary query does not trigger lexical
    assert not policy.uses_lexical("how does dreaming work")
    # Literal-heavy query with hex hash or version triggers lexical
    assert policy.uses_lexical("commit 718d940b5406")
    assert policy.uses_lexical("version 0.2.1")


def test_retrieval_policy_hybrid_opt_in_uses_lexical_for_all_queries() -> None:
    policy = KnowledgeRetrievalPolicy(mode="hybrid")
    assert policy.mode == "hybrid"
    assert policy.uses_lexical("ordinary query")
    assert policy.uses_lexical("CYBERBRAIN_KNOWLEDGE_SEARCH_SCORE_THRESHOLD")


def test_rank_knowledge_hybrid_fuses_semantic_and_lexical() -> None:
    repo = FakeRepository()
    id1 = uuid4()
    id2 = uuid4()
    repo.upsert(
        "cyberbrain_knowledge",
        point_id=id1,
        vector=[0.1, 0.2, 0.3],
        payload={
            "id": str(id1),
            "status": "active",
            "content": "Python settings configuration guide",
        },
    )
    repo.upsert(
        "cyberbrain_knowledge",
        point_id=id2,
        vector=[0.2, 0.3, 0.4],
        payload={
            "id": str(id2),
            "status": "active",
            "content": "Docker compose deployment and rollout",
        },
    )

    policy = KnowledgeRetrievalPolicy(mode="hybrid")
    vector_points = [
        {"id": str(id2), "score": 0.95, "payload": repo.points[id2]["payload"]},
        {"id": str(id1), "score": 0.80, "payload": repo.points[id1]["payload"]},
    ]

    ranked = rank_knowledge(
        repository=repo,
        collection="cyberbrain_knowledge",
        query="configuration guide",
        vector_points=vector_points,
        qdrant_filter={"must": [{"key": "status", "match": {"value": "active"}}]},
        limit=5,
        policy=policy,
    )

    assert len(ranked) == 2
    # id1 has strong lexical match ("configuration guide"), so RRF elevates it
    assert ranked[0]["id"] == str(id1)
    assert ranked[0]["_retrieval"]["method"] == "hybrid"
