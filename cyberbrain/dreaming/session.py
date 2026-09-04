# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from cyberbrain.dreaming.planner import EpisodeSnippet
from cyberbrain.schemas.models import DreamStatus
from cyberbrain.storage.base import PointRepository


class QdrantSessionEpisodeLoader:
    def __init__(
        self,
        *,
        repository: PointRepository,
        collection: str,
        limit: int = 1000,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        self._repository = repository
        self._collection = collection
        self._limit = limit

    def load(self, session_id: str) -> list[EpisodeSnippet]:
        value = session_id.strip()
        if not value:
            raise ValueError("session_id must not be empty")

        points = self._repository.scroll(
            self._collection,
            qdrant_filter={
                "must": [
                    {"key": "session_id", "match": {"value": value}},
                ]
            },
            limit=self._limit,
        )
        episodes: list[EpisodeSnippet] = []
        for point in points:
            payload = point.get("payload") or {}
            content = str(payload.get("content") or "").strip()
            if not content:
                continue
            event_time = self._event_time(payload.get("event_time"))
            if event_time is None:
                continue
            episodes.append(EpisodeSnippet(content=content, event_time=event_time))

        episodes.sort(key=lambda episode: episode.event_time)
        if not episodes:
            raise ValueError(f"session {value!r} has no usable episodic evidence")
        return episodes

    def update_status(
        self,
        session_id: str,
        *,
        status: DreamStatus,
        dream_run_id: str | None = None,
        dreamed_at: datetime | None = None,
    ) -> int:
        value = session_id.strip()
        if not value:
            raise ValueError("session_id must not be empty")
        points = self._repository.scroll(
            self._collection,
            qdrant_filter={
                "must": [{"key": "session_id", "match": {"value": value}}]
            },
            limit=self._limit,
        )
        if len(points) >= self._limit:
            raise ValueError(
                f"session {value!r} reached episode status update limit {self._limit}"
            )
        payload = {"dream_status": status.value}
        if dream_run_id is not None:
            payload["dream_run_id"] = dream_run_id
        if dreamed_at is not None:
            if dreamed_at.tzinfo is None or dreamed_at.utcoffset() is None:
                raise ValueError("dreamed_at must include a timezone")
            payload["dreamed_at"] = dreamed_at.astimezone(UTC).isoformat()
        for point in points:
            self._repository.set_payload(
                self._collection,
                point_id=UUID(str(point["id"])),
                payload=payload,
            )
        return len(points)

    @staticmethod
    def _event_time(value: object) -> datetime | None:
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
        if isinstance(value, int | float):
            seconds = float(value) / 1000 if value > 10_000_000_000 else float(value)
            try:
                return datetime.fromtimestamp(seconds, tz=UTC)
            except (OSError, OverflowError, ValueError):
                return None
        return None
