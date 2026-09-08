# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any


class FakeCyberBrainClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.knowledge_rows: list[dict[str, Any]] = []
        self.memory_rows: list[dict[str, Any]] = []
        self.pending_rows: list[dict[str, Any]] = []
        self.timeline_rows: list[dict[str, Any]] = []
        self.knowledge_by_id: dict[str, dict[str, Any]] = {}
        self.memory_by_id: dict[str, dict[str, Any]] = {}

    def _record(self, name: str, kwargs: dict[str, Any]) -> None:
        self.calls.append((name, kwargs))

    def count(self, name: str) -> int:
        return sum(1 for call, _ in self.calls if call == name)

    async def knowledge_search(self, **kwargs: Any) -> list[dict[str, Any]]:
        self._record("knowledge_search", kwargs)
        return self.knowledge_rows[: int(kwargs.get("limit", 5))]

    async def knowledge_get(self, *, record_id: str) -> dict[str, Any] | None:
        self._record("knowledge_get", {"record_id": record_id})
        return self.knowledge_by_id.get(record_id)

    async def knowledge_timeline(self, **identity: Any) -> list[dict[str, Any]]:
        self._record("knowledge_timeline", identity)
        return list(self.timeline_rows)

    async def memory_search(self, **kwargs: Any) -> list[dict[str, Any]]:
        self._record("memory_search", kwargs)
        return self.memory_rows[: int(kwargs.get("limit", 5))]

    async def memory_get(self, *, record_id: str) -> dict[str, Any] | None:
        self._record("memory_get", {"record_id": record_id})
        return self.memory_by_id.get(record_id)

    async def memory_store(
        self,
        *,
        content: str,
        session_id: str,
        event_time: datetime,
        **metadata: Any,
    ) -> dict[str, Any]:
        payload = {
            "content": content,
            "session_id": session_id,
            "event_time": event_time,
            **metadata,
        }
        self._record("memory_store", payload)
        return {"id": "episode-closeout", **payload}

    async def prediction_record(
        self,
        *,
        expected_outcome: str,
        confidence: float,
        session_id: str,
        event_time: datetime,
        **metadata: Any,
    ) -> dict[str, Any]:
        payload = {
            "expected_outcome": expected_outcome,
            "confidence": confidence,
            "session_id": session_id,
            "event_time": event_time,
            **metadata,
        }
        self._record("prediction_record", payload)
        return {"id": "prediction-new", **payload}

    async def prediction_resolve(
        self,
        *,
        prediction_id: str,
        observed_outcome: str,
        assessment: str,
        event_time: datetime,
        **metadata: Any,
    ) -> dict[str, Any]:
        payload = {
            "prediction_id": prediction_id,
            "observed_outcome": observed_outcome,
            "assessment": assessment,
            "event_time": event_time,
            **metadata,
        }
        self._record("prediction_resolve", payload)
        return {"id": "outcome-new", **payload}

    async def prediction_pending(self, **kwargs: Any) -> list[dict[str, Any]]:
        self._record("prediction_pending", kwargs)
        return self.pending_rows[: int(kwargs.get("limit", 5))]

    async def dream_enqueue(
        self,
        *,
        session_id: str,
        focal_topics: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        payload = {"session_id": session_id, "focal_topics": focal_topics}
        self._record("dream_enqueue", payload)
        return {"status": "queued", **payload}
