# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID


class PointRepository(Protocol):
    def upsert(
        self,
        collection: str,
        *,
        point_id: UUID,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None: ...

    def set_payload(
        self,
        collection: str,
        *,
        point_id: UUID,
        payload: dict[str, Any],
    ) -> None: ...

    def retrieve(
        self,
        collection: str,
        point_id: UUID,
    ) -> dict[str, Any] | None: ...

    def search(
        self,
        collection: str,
        *,
        vector: list[float],
        limit: int,
        qdrant_filter: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]: ...

    def scroll(
        self,
        collection: str,
        *,
        qdrant_filter: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...
