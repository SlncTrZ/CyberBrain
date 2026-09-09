# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from typing import Any
from uuid import UUID

from cyberbrain.embedding.base import EmbeddingProvider
from cyberbrain.retrieval.shadow import KnowledgeLiteralShadowObserver
from cyberbrain.schemas.models import KnowledgeRecordClass
from cyberbrain.storage.base import PointRepository
from cyberbrain.storage.scoping import storage_filter_to_repository_filter
from cyberbrain.tenancy import (
    CallerAuthority,
    DeploymentMode,
    IdentityScope,
    OperationClass,
    ScopeAuthorizationPolicy,
    build_storage_filter,
)


class KnowledgeSearchService:
    def __init__(
        self,
        *,
        repository: PointRepository,
        embedding: EmbeddingProvider,
        collection: str,
        score_threshold: float | None = 0.7,
        literal_shadow: KnowledgeLiteralShadowObserver | None = None,
    ) -> None:
        self._repository = repository
        self._embedding = embedding
        self._collection = collection
        self._score_threshold = score_threshold
        self._literal_shadow = literal_shadow

    @property
    def collection(self) -> str:
        return self._collection

    def get(self, *, point_id: UUID, authority: CallerAuthority) -> dict[str, Any] | None:
        if authority.deployment_mode is DeploymentMode.MULTI_USER:
            return None
        decision = ScopeAuthorizationPolicy.decide(
            authority.grant,
            requested_scope=IdentityScope(),
            operation=OperationClass.READ,
        )
        if not decision.allow or decision.effective_scope is None:
            return None
        qdrant_filter = storage_filter_to_repository_filter(
            build_storage_filter(decision.effective_scope),
            include_fields=frozenset({"project"}),
        )
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
                "key": "record_class",
                "match": {"value": KnowledgeRecordClass.KNOWLEDGE.value},
            },
            {"key": "ordinary_recall", "match": {"value": True}},
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
        rows = [
            {
                "id": point["id"],
                "score": point.get("score"),
                **(point.get("payload") or {}),
            }
            for point in points
        ]
        if self._literal_shadow is not None:
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
        results = [{"id": point["id"], **(point.get("payload") or {})} for point in points]
        results.sort(key=lambda item: int(item.get("version", 0)), reverse=True)
        return results
