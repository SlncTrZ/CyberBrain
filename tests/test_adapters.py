# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from cyberbrain.core.errors import EmbeddingError
from cyberbrain.embedding.ollama import OllamaEmbeddingProvider
from cyberbrain.storage.qdrant import QdrantRepository


def test_ollama_embedding_provider_returns_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(*args, **kwargs):  # noqa: ANN002, ANN003
        request = httpx.Request("POST", "http://embedding/api/embeddings")
        return httpx.Response(200, request=request, json={"embedding": [0.1, 0.2, 0.3]})

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaEmbeddingProvider(
        base_url="http://embedding",
        model="test",
        dimension=3,
        version="test@v1",
    )
    assert provider.embed("hello") == [0.1, 0.2, 0.3]


def test_ollama_embedding_provider_rejects_bad_dimension(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(*args, **kwargs):  # noqa: ANN002, ANN003
        request = httpx.Request("POST", "http://embedding/api/embeddings")
        return httpx.Response(200, request=request, json={"embedding": [0.1]})

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaEmbeddingProvider(
        base_url="http://embedding",
        model="test",
        dimension=3,
        version="test@v1",
    )
    with pytest.raises(EmbeddingError, match="dimension mismatch"):
        provider.embed("hello")


def test_qdrant_search_preserves_point_id_and_payload() -> None:
    point_id = str(uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/collections/cyberbrain_knowledge/points/search")
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "result": [
                    {
                        "id": point_id,
                        "score": 0.91,
                        "payload": {"entity_name": "x", "status": "active"},
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    repo = QdrantRepository(base_url="http://qdrant:6333", client=client)

    result = repo.search(
        "cyberbrain_knowledge",
        vector=[0.0, 1.0],
        limit=5,
        qdrant_filter={"must": [{"key": "status", "match": {"value": "active"}}]},
    )

    assert result[0]["id"] == point_id
    assert result[0]["payload"]["entity_name"] == "x"


def test_qdrant_set_payload_targets_concrete_point_id() -> None:
    point_id = uuid4()
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"status": "ok", "result": {"status": "completed"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    repo = QdrantRepository(base_url="http://qdrant:6333", client=client)
    repo.set_payload(
        "cyberbrain_knowledge",
        point_id=point_id,
        payload={"status": "superseded"},
    )

    assert seen["path"] == "/collections/cyberbrain_knowledge/points/payload"
    assert str(point_id) in str(seen["body"])
    assert "superseded" in str(seen["body"])
