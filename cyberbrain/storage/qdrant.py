# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from time import monotonic
from typing import Any
from uuid import UUID

import httpx

from cyberbrain.core.errors import StorageError
from cyberbrain.core.metrics import MetricsRegistry


class QdrantRepository:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 15.0,
        client: httpx.Client | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["api-key"] = api_key
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._metrics = metrics

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        request_kwargs = {
            "headers": self._headers,
            "timeout": self._timeout_seconds,
            **kwargs,
        }
        started = monotonic()
        try:
            if self._client is None:
                response = httpx.request(method, f"{self._base_url}{path}", **request_kwargs)
            else:
                response = self._client.request(method, f"{self._base_url}{path}", **request_kwargs)
            if self._metrics is not None:
                self._metrics.increment("qdrant_requests_total")
                self._metrics.observe("qdrant_request_seconds", monotonic() - started)
            return response
        except httpx.HTTPError as exc:
            if self._metrics is not None:
                self._metrics.increment("qdrant_request_failures_total")
                self._metrics.observe("qdrant_request_seconds", monotonic() - started)
            raise StorageError(f"Qdrant request failed: {method} {path}: {exc}") from exc

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._send(method, path, **kwargs)
        try:
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise StorageError(f"Qdrant request failed: {method} {path}: {exc}") from exc

        if data.get("status") != "ok":
            raise StorageError(f"Qdrant operation failed: {data.get('status')!r}")
        return data

    def collection_info(self, name: str) -> dict[str, Any] | None:
        response = self._send("GET", f"/collections/{name}")
        if response.status_code == 404:
            return None
        try:
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise StorageError(f"Qdrant request failed: GET /collections/{name}: {exc}") from exc
        if data.get("status") != "ok":
            raise StorageError(f"Qdrant operation failed: {data.get('status')!r}")
        result = data.get("result")
        if not isinstance(result, dict):
            raise StorageError("Qdrant collection info response is missing result")
        return result

    def ensure_collection(self, name: str, *, vector_size: int, distance: str = "Cosine") -> None:
        info = self.collection_info(name)
        if info is None:
            response = self._send(
                "PUT",
                f"/collections/{name}",
                json={"vectors": {"size": vector_size, "distance": distance}},
            )
            if response.status_code != 409:
                try:
                    response.raise_for_status()
                    data = response.json()
                except (httpx.HTTPError, ValueError) as exc:
                    raise StorageError(
                        f"Qdrant request failed: PUT /collections/{name}: {exc}"
                    ) from exc
                if data.get("status") != "ok":
                    raise StorageError(f"Qdrant operation failed: {data.get('status')!r}")
            info = self.collection_info(name)
            if info is None:
                raise StorageError(f"Qdrant collection was not created: {name}")

        vectors = (((info.get("config") or {}).get("params") or {}).get("vectors"))
        if not isinstance(vectors, dict):
            raise StorageError(f"Qdrant collection {name!r} has unsupported vector config")
        actual_size = vectors.get("size")
        actual_distance = str(vectors.get("distance") or "")
        if actual_size != vector_size:
            raise StorageError(
                f"Qdrant collection {name!r} vector size mismatch: "
                f"expected {vector_size}, got {actual_size}"
            )
        if actual_distance.casefold() != distance.casefold():
            raise StorageError(
                f"Qdrant collection {name!r} distance mismatch: "
                f"expected {distance}, got {actual_distance}"
            )

    def upsert(
        self,
        collection: str,
        *,
        point_id: UUID,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        self._request(
            "PUT",
            f"/collections/{collection}/points?wait=true",
            json={
                "points": [
                    {
                        "id": str(point_id),
                        "vector": vector,
                        "payload": payload,
                    }
                ]
            },
        )

    def set_payload(self, collection: str, *, point_id: UUID, payload: dict[str, Any]) -> None:
        self._request(
            "POST",
            f"/collections/{collection}/points/payload?wait=true",
            json={"payload": payload, "points": [str(point_id)]},
        )

    def retrieve(self, collection: str, point_id: UUID) -> dict[str, Any] | None:
        data = self._request(
            "POST",
            f"/collections/{collection}/points",
            json={"ids": [str(point_id)], "with_payload": True, "with_vector": False},
        )
        points = data.get("result", [])
        return points[0] if points else None

    def search(
        self,
        collection: str,
        *,
        vector: list[float],
        limit: int,
        qdrant_filter: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {
            "vector": vector,
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
        }
        if qdrant_filter:
            body["filter"] = qdrant_filter
        if score_threshold is not None:
            body["score_threshold"] = score_threshold

        data = self._request("POST", f"/collections/{collection}/points/search", json=body)
        return list(data.get("result", []))

    def scroll(
        self,
        collection: str,
        *,
        qdrant_filter: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if limit < 1:
            return []

        points: list[dict[str, Any]] = []
        offset: Any = None
        while len(points) < limit:
            page_limit = min(256, limit - len(points))
            body: dict[str, Any] = {
                "limit": page_limit,
                "with_payload": True,
                "with_vector": False,
            }
            if qdrant_filter:
                body["filter"] = qdrant_filter
            if offset is not None:
                body["offset"] = offset

            data = self._request(
                "POST",
                f"/collections/{collection}/points/scroll",
                json=body,
            )
            result = data.get("result", {})
            batch = list(result.get("points", []))
            points.extend(batch)
            next_offset = result.get("next_page_offset")
            if not batch or next_offset is None:
                break
            offset = next_offset

        return points[:limit]
