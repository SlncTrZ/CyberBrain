# SPDX-License-Identifier: MPL-2.0
"""Optional storage-boundary gate; requires a new empty loopback-only Qdrant."""

import os
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
import pytest

from cyberbrain.dreaming.session import QdrantSessionEpisodeLoader
from cyberbrain.knowledge.evolution import KnowledgeEvolutionService
from cyberbrain.memory.service import MemoryService
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


@pytest.mark.skipif(not os.environ.get("CYBERBRAIN_QA_QDRANT_URL"),
                    reason="isolated empty Qdrant QA endpoint required")
def test_real_qdrant_isolates_versions_exact_reads_and_session_updates():
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
        repository=repo, embedding=embedding, collection="cyberbrain_episodic",
        score_threshold=None,
    )
    evolution = KnowledgeEvolutionService(
        repository=repo, embedding=embedding, collection="cyberbrain_knowledge",
    )
    authorities = {name: authority_for_authenticated_scope(
        DeploymentMode.MULTI_USER,
        scope=IdentityScope.from_values(tenant=name, user="same", agent="shared", project="same"),
        operations=frozenset(OperationClass),
    ) for name in ("one", "two")}
    memories = {}
    knowledge = {}
    common = dict(domain="qa", topic="isolation", entity_type="policy", entity_name="same")
    for name, caller in authorities.items():
        with bind_authority(caller):
            memories[name] = memory.store(
                content="experience " + name,
                session_id="same-session", event_time=datetime.now(UTC),
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
