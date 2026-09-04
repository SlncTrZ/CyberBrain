# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from cyberbrain.dreaming.planner import TemporalBucket
from cyberbrain.dreaming.reasoner import EvidenceItem
from cyberbrain.embedding.base import EmbeddingProvider
from cyberbrain.storage.base import PointRepository


class QdrantEvidenceRetriever:
    """Semantic + temporal evidence recall for canonical Dreaming."""

    def __init__(
        self,
        *,
        repository: PointRepository,
        embedding: EmbeddingProvider,
        knowledge_collection: str,
        episodic_collection: str,
    ) -> None:
        self._repository = repository
        self._embedding = embedding
        self._knowledge_collection = knowledge_collection
        self._episodic_collection = episodic_collection

    def recall(
        self,
        *,
        topic: str,
        bucket: TemporalBucket,
        limit: int,
    ) -> list[EvidenceItem]:
        if limit < 1:
            return []
        vector = self._embedding.embed(topic)

        episodic = self._repository.search(
            self._episodic_collection,
            vector=vector,
            limit=limit,
            qdrant_filter=self._episodic_filter(bucket),
        )
        knowledge = self._repository.search(
            self._knowledge_collection,
            vector=vector,
            limit=limit,
            qdrant_filter=self._knowledge_filter(bucket),
        )

        items = [
            self._to_evidence(point, record_type="episode")
            for point in episodic
        ] + [
            self._to_evidence(point, record_type="knowledge")
            for point in knowledge
        ]
        items = [item for item in items if item is not None]
        items.sort(key=lambda item: item.score if item.score is not None else -1.0, reverse=True)
        return self._deduplicate(items)[:limit]

    @staticmethod
    def _episodic_filter(bucket: TemporalBucket) -> dict[str, Any]:
        must: list[dict[str, Any]] = [
            {
                "key": "event_time",
                "range": QdrantEvidenceRetriever._range(bucket),
            }
        ]
        return {"must": must}

    @staticmethod
    def _knowledge_filter(bucket: TemporalBucket) -> dict[str, Any]:
        must: list[dict[str, Any]] = [
            {"key": "status", "match": {"value": "active"}},
            {
                "key": "updated_at",
                "range": QdrantEvidenceRetriever._range(bucket),
            },
        ]
        return {"must": must}

    @staticmethod
    def _range(bucket: TemporalBucket) -> dict[str, str]:
        result = {"lte": bucket.end.astimezone(UTC).isoformat()}
        if bucket.start is not None:
            result["gt"] = bucket.start.astimezone(UTC).isoformat()
        return result

    @staticmethod
    def _to_evidence(
        point: dict[str, Any],
        *,
        record_type: str,
    ) -> EvidenceItem | None:
        payload = point.get("payload") or {}
        content = str(payload.get("content") or "").strip()
        point_id = str(point.get("id") or payload.get("id") or "").strip()
        if not content or not point_id:
            return None

        event_time = QdrantEvidenceRetriever._event_time(payload, record_type=record_type)
        metadata = QdrantEvidenceRetriever._metadata(payload)
        score = point.get("score")
        return EvidenceItem(
            id=point_id,
            record_type=record_type,
            content=content,
            score=float(score) if isinstance(score, int | float) else None,
            event_time=event_time,
            metadata=metadata,
        )

    @staticmethod
    def _event_time(payload: dict[str, Any], *, record_type: str) -> datetime | None:
        key = "event_time" if record_type == "episode" else "updated_at"
        value = payload.get(key)
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        return None

    @staticmethod
    def _metadata(payload: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "domain",
            "topic",
            "project",
            "verification",
            "version",
            "status",
            "entity_type",
            "entity_name",
            "origin",
            "source",
            "session_id",
            "channel",
            "role",
            "agent",
            "dream_status",
        )
        metadata = {key: payload[key] for key in keys if payload.get(key) is not None}
        context = payload.get("context")
        if isinstance(context, dict) and context:
            metadata["context"] = dict(context)
        return metadata

    @staticmethod
    def _deduplicate(items: list[EvidenceItem]) -> list[EvidenceItem]:
        result: list[EvidenceItem] = []
        seen: set[str] = set()
        for item in items:
            if item.id in seen:
                continue
            seen.add(item.id)
            result.append(item)
        return result
