# SPDX-License-Identifier: MPL-2.0

import json

import httpx
import pytest

from cyberbrain.core.errors import StorageError
from cyberbrain.storage.qdrant import QdrantRepository


def _collection_info(size: int = 768, distance: str = "Cosine") -> dict:
    return {
        "status": "ok",
        "result": {
            "config": {
                "params": {
                    "vectors": {
                        "size": size,
                        "distance": distance,
                    }
                }
            }
        },
    }


def test_ensure_collection_accepts_matching_existing_collection() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(200, json=_collection_info(), request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    repo = QdrantRepository(base_url="http://qdrant:6333", client=client)

    repo.ensure_collection("knowledge", vector_size=768)

    assert methods == ["GET"]


def test_ensure_collection_creates_only_on_not_found() -> None:
    created = False
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal created
        methods.append(request.method)
        if request.method == "GET" and not created:
            return httpx.Response(404, json={"status": "error"}, request=request)
        if request.method == "PUT":
            body = json.loads(request.content)
            assert body["vectors"] == {"size": 768, "distance": "Cosine"}
            created = True
            return httpx.Response(200, json={"status": "ok", "result": True}, request=request)
        return httpx.Response(200, json=_collection_info(), request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    repo = QdrantRepository(base_url="http://qdrant:6333", client=client)

    repo.ensure_collection("knowledge", vector_size=768)

    assert methods == ["GET", "PUT", "GET"]



def test_ensure_collection_accepts_concurrent_create_conflict() -> None:
    get_count = 0
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal get_count
        methods.append(request.method)
        if request.method == "GET":
            get_count += 1
            if get_count == 1:
                return httpx.Response(404, json={"status": "error"}, request=request)
            return httpx.Response(200, json=_collection_info(), request=request)
        if request.method == "PUT":
            return httpx.Response(
                409,
                json={"status": "error", "result": None},
                request=request,
            )
        raise AssertionError(request.method)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    repo = QdrantRepository(base_url="http://qdrant:6333", client=client)

    repo.ensure_collection("knowledge", vector_size=768)

    assert methods == ["GET", "PUT", "GET"]

def test_ensure_collection_does_not_treat_auth_failure_as_missing() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(401, json={"status": "error"}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    repo = QdrantRepository(base_url="http://qdrant:6333", client=client)

    with pytest.raises(StorageError, match="401"):
        repo.ensure_collection("knowledge", vector_size=768)

    assert methods == ["GET"]


def test_ensure_collection_rejects_vector_size_mismatch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_collection_info(size=384), request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    repo = QdrantRepository(base_url="http://qdrant:6333", client=client)

    with pytest.raises(StorageError, match="vector size mismatch"):
        repo.ensure_collection("knowledge", vector_size=768)


def test_scroll_paginates_until_requested_limit() -> None:
    offsets: list[object] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        offsets.append(body.get("offset"))
        if "offset" not in body:
            result = {
                "points": [{"id": str(index), "payload": {}} for index in range(256)],
                "next_page_offset": "page-2",
            }
        else:
            assert body["offset"] == "page-2"
            assert body["limit"] == 44
            result = {
                "points": [{"id": str(index), "payload": {}} for index in range(256, 300)],
                "next_page_offset": None,
            }
        return httpx.Response(200, json={"status": "ok", "result": result}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    repo = QdrantRepository(base_url="http://qdrant:6333", client=client)

    points = repo.scroll("knowledge", limit=300)

    assert len(points) == 300
    assert offsets == [None, "page-2"]
