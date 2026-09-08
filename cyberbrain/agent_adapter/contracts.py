# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol


class CyberBrainClient(Protocol):
    """Transport-neutral operations required by the Agent Adapter."""

    async def knowledge_search(
        self,
        *,
        query: str,
        limit: int = 5,
        view: str = "compact",
        **filters: Any,
    ) -> list[dict[str, Any]]: ...

    async def knowledge_get(self, *, record_id: str) -> dict[str, Any] | None: ...

    async def knowledge_timeline(self, **identity: Any) -> list[dict[str, Any]]: ...

    async def memory_search(
        self,
        *,
        query: str,
        limit: int = 5,
        view: str = "compact",
        **filters: Any,
    ) -> list[dict[str, Any]]: ...

    async def memory_get(self, *, record_id: str) -> dict[str, Any] | None: ...

    async def memory_store(
        self,
        *,
        content: str,
        session_id: str,
        event_time: datetime,
        **metadata: Any,
    ) -> dict[str, Any]: ...

    async def prediction_record(
        self,
        *,
        expected_outcome: str,
        confidence: float,
        session_id: str,
        event_time: datetime,
        **metadata: Any,
    ) -> dict[str, Any]: ...

    async def prediction_resolve(
        self,
        *,
        prediction_id: str,
        observed_outcome: str,
        assessment: str,
        event_time: datetime,
        **metadata: Any,
    ) -> dict[str, Any]: ...

    async def prediction_pending(
        self,
        *,
        limit: int = 5,
        **filters: Any,
    ) -> list[dict[str, Any]]: ...

    async def dream_enqueue(
        self,
        *,
        session_id: str,
        focal_topics: Sequence[str] | None = None,
    ) -> dict[str, Any]: ...
