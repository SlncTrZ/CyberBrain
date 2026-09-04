# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from cyberbrain.core.content import content_hash, normalize_content
from cyberbrain.core.secrets import SecretScanner
from cyberbrain.embedding.base import EmbeddingProvider
from cyberbrain.schemas.models import DreamStatus, EpisodeRecord, EpisodeRole
from cyberbrain.storage.base import PointRepository


class MemoryService:
    def __init__(
        self,
        *,
        repository: PointRepository,
        embedding: EmbeddingProvider,
        collection: str,
        score_threshold: float | None = 0.7,
        secret_scanner: SecretScanner | None = None,
    ) -> None:
        self._repository = repository
        self._embedding = embedding
        self._collection = collection
        self._score_threshold = score_threshold
        self._secret_scanner = secret_scanner or SecretScanner()

    def store(
        self,
        *,
        content: str,
        session_id: str,
        event_time: datetime,
        channel: str | None = None,
        role: EpisodeRole | None = None,
        agent: str | None = None,
        project: str | None = None,
        topic: str | None = None,
        keywords: list[str] | None = None,
        importance: str | None = None,
        source: str | None = None,
        context: dict[str, Any] | None = None,
        extensions: dict[str, Any] | None = None,
        point_id: UUID | None = None,
    ) -> EpisodeRecord:
        normalized = normalize_content(content)
        self._secret_scanner.assert_safe(
            normalized,
            source,
            repr(context or {}),
            repr(extensions or {}),
        )
        record = EpisodeRecord(
            id=point_id or EpisodeRecord.model_fields["id"].default_factory(),
            content=normalized,
            session_id=session_id,
            event_time=event_time,
            channel=channel,
            role=role,
            agent=agent,
            project=project,
            topic=topic,
            keywords=keywords or [],
            importance=importance,
            source=source,
            content_hash=content_hash(normalized),
            embedding_version=self._embedding.version,
            context=context or {},
            extensions=extensions or {},
        )
        vector = self._embedding.embed(record.content)
        self._repository.upsert(
            self._collection,
            point_id=record.id,
            vector=vector,
            payload=record.model_dump(mode="json"),
        )
        return record

    def search(
        self,
        *,
        query: str,
        limit: int = 5,
        session_id: str | None = None,
        channel: str | None = None,
        role: str | None = None,
        agent: str | None = None,
        project: str | None = None,
        topic: str | None = None,
        dream_status: DreamStatus | str | None = None,
    ) -> list[dict[str, Any]]:
        filter_values = {
            "session_id": session_id,
            "channel": channel,
            "role": role,
            "agent": agent,
            "project": project,
            "topic": topic,
            "dream_status": (
                dream_status.value if isinstance(dream_status, DreamStatus) else dream_status
            ),
        }
        conditions = [
            {"key": key, "match": {"value": value}}
            for key, value in filter_values.items()
            if value is not None
        ]
        vector = self._embedding.embed(query)
        points = self._repository.search(
            self._collection,
            vector=vector,
            limit=limit,
            qdrant_filter={"must": conditions} if conditions else None,
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
