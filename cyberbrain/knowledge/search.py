# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from typing import Any

from cyberbrain.embedding.base import EmbeddingProvider
from cyberbrain.storage.base import PointRepository


class KnowledgeSearchService:
    def __init__(
        self,
        *,
        repository: PointRepository,
        embedding: EmbeddingProvider,
        collection: str,
        score_threshold: float | None = 0.7,
    ) -> None:
        self._repository = repository
        self._embedding = embedding
        self._collection = collection
        self._score_threshold = score_threshold

    @property
    def collection(self) -> str:
        return self._collection

    def search(
        self,
        *,
        query: str,
        limit: int = 5,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        conditions = [
            {"key": "status", "match": {"value": filters.pop("status", "active")}}
        ]
        for key, value in filters.items():
            if value is not None:
                conditions.append({"key": key, "match": {"value": value}})

        vector = self._embedding.embed(query)
        points = self._repository.search(
            self._collection,
            vector=vector,
            limit=limit,
            qdrant_filter={"must": conditions},
            score_threshold=self._score_threshold,
        )
        return [
            {
                "id": point["id"],
                "score": point.get("score"),
                **(point.get("payload") or {}),
            }
            for point in points
        ]

    def timeline(
        self,
        *,
        domain: str,
        topic: str,
        entity_type: str,
        entity_name: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        qdrant_filter = {
            "must": [
                {"key": "domain", "match": {"value": domain}},
                {"key": "topic", "match": {"value": topic}},
                {"key": "entity_type", "match": {"value": entity_type}},
                {"key": "entity_name", "match": {"value": entity_name}},
            ]
        }
        points = self._repository.scroll(
            self._collection,
            qdrant_filter=qdrant_filter,
            limit=limit,
        )
        results = [
            {"id": point["id"], **(point.get("payload") or {})}
            for point in points
        ]
        results.sort(key=lambda item: int(item.get("version", 0)), reverse=True)
        return results
