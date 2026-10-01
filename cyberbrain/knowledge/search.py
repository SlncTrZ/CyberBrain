# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from typing import Any
from uuid import UUID

from cyberbrain.embedding.base import EmbeddingProvider
from cyberbrain.retrieval.runtime import KnowledgeRetrievalPolicy, rank_knowledge
from cyberbrain.retrieval.shadow import KnowledgeLiteralShadowObserver
from cyberbrain.schemas.models import KnowledgeRecordClass
from cyberbrain.storage.base import PointRepository
from cyberbrain.tenancy import (
    CallerAuthority,
)
from cyberbrain.tenancy.enforcement import TenancyOperation
from cyberbrain.tenancy.runtime import enforce_operation, scope_conditions


class KnowledgeSearchService:
    def __init__(
        self,
        *,
        repository: PointRepository,
        embedding: EmbeddingProvider,
        collection: str,
        score_threshold: float | None = 0.7,
        literal_shadow: KnowledgeLiteralShadowObserver | None = None,
        retrieval_policy: KnowledgeRetrievalPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._embedding = embedding
        self._collection = collection
        self._score_threshold = score_threshold
        self._literal_shadow = literal_shadow
        self._retrieval_policy = retrieval_policy or KnowledgeRetrievalPolicy()

    @property
    def collection(self) -> str:
        return self._collection

    def get(self, *, point_id: UUID, authority: CallerAuthority) -> dict[str, Any] | None:
        plan = enforce_operation(TenancyOperation.KNOWLEDGE_GET, authority=authority)
        conditions = scope_conditions(plan)
        qdrant_filter = {"must": conditions} if conditions else None
        point = self._repository.retrieve(
            self._collection,
            point_id,
            qdrant_filter=qdrant_filter,
        )
        if point is None:
            return None
        return {"id": point["id"], **(point.get("payload") or {})}

    def search(
        self,
        *,
        query: str,
        limit: int = 5,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        plan = enforce_operation(TenancyOperation.KNOWLEDGE_SEARCH, filters)
        status = filters.pop("status", "active")
        normalized_filters = {
            "status": status,
            "record_class": KnowledgeRecordClass.KNOWLEDGE.value,
            "ordinary_recall": True,
            **filters,
        }
        conditions = [
            {"key": "status", "match": {"value": status}},
            {
                "should": [
                    {
                        "key": "record_class",
                        "match": {"value": KnowledgeRecordClass.KNOWLEDGE.value},
                    },
                    {"is_empty": {"key": "record_class"}},
                ]
            },
            {
                "should": [
                    {"key": "ordinary_recall", "match": {"value": True}},
                    {"is_empty": {"key": "ordinary_recall"}},
                ]
            },
        ]
        for key, value in filters.items():
            if value is not None:
                conditions.append({"key": key, "match": {"value": value}})

        conditions.extend(scope_conditions(plan))
        use_lexical = self._retrieval_policy.uses_lexical(query) and limit > 0
        vector = self._embedding.embed(query)
        points = self._repository.search(
            self._collection,
            vector=vector,
            limit=(self._retrieval_policy.candidate_limit(limit) if use_lexical else limit),
            qdrant_filter={"must": conditions},
            score_threshold=self._score_threshold,
        )
        if use_lexical:
            return rank_knowledge(
                repository=self._repository, collection=self._collection, query=query,
                vector_points=points, qdrant_filter={"must": conditions},
                limit=limit, policy=self._retrieval_policy,
            )
        rows = [
            {
                "id": point["id"],
                "score": point.get("score"),
                **(point.get("payload") or {}),
            }
            for point in points
        ]
        if self._literal_shadow is not None and not scope_conditions(plan):
            self._literal_shadow.submit(
                query=query,
                vector_rows=rows,
                filters=normalized_filters,
                limit=limit,
            )
        return rows

    def timeline(
        self,
        *,
        domain: str,
        topic: str,
        entity_type: str,
        entity_name: str,
        limit: int = 100,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        plan = enforce_operation(TenancyOperation.KNOWLEDGE_TIMELINE, filters)
        qdrant_filter = {
            "must": [
                {"key": "domain", "match": {"value": domain}},
                {"key": "topic", "match": {"value": topic}},
                {"key": "entity_type", "match": {"value": entity_type}},
                {"key": "entity_name", "match": {"value": entity_name}},
            ]
        }
        qdrant_filter["must"].extend(scope_conditions(plan))
        qdrant_filter["must"].extend(
            {"key": key, "match": {"value": value}}
            for key, value in filters.items() if value is not None
        )
        points = self._repository.scroll(
            self._collection,
            qdrant_filter=qdrant_filter,
            limit=limit,
        )
        results = [{"id": point["id"], **(point.get("payload") or {})} for point in points]
        results.sort(key=lambda item: int(item.get("version", 0)), reverse=True)
        return results
