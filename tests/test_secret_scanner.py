# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from cyberbrain.core.errors import SensitiveDataError
from cyberbrain.core.secrets import SecretScanner
from cyberbrain.memory.service import MemoryService


class CountingEmbedding:
    dimension = 3
    version = "fake@v1"

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, text: str) -> list[float]:
        self.calls += 1
        return [0.1, 0.2, 0.3]


class NoopRepository:
    def __init__(self) -> None:
        self.upserts = 0

    def upsert(
        self,
        collection: str,
        *,
        point_id: UUID,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        self.upserts += 1

    def set_payload(self, collection: str, *, point_id: UUID, payload: dict[str, Any]) -> None:
        raise AssertionError("unexpected")

    def retrieve(self, collection: str, point_id: UUID) -> dict[str, Any] | None:
        return None

    def search(
        self,
        collection: str,
        *,
        vector: list[float],
        limit: int,
        qdrant_filter: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        return []

    def scroll(
        self,
        collection: str,
        *,
        qdrant_filter: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return []


def test_scanner_rejects_secret_without_echoing_value() -> None:
    scanner = SecretScanner()
    value = "sk-abcdefghijklmnopqrstuvwxyz1234567890"

    with pytest.raises(SensitiveDataError) as exc_info:
        scanner.assert_safe(f"api key = {value}")

    assert "openai_api_key" in str(exc_info.value)
    assert value not in str(exc_info.value)


def test_example_marker_does_not_mask_real_secret_elsewhere() -> None:
    scanner = SecretScanner()
    value = "sk-abcdefghijklmnopqrstuvwxyz1234567890"

    with pytest.raises(SensitiveDataError):
        scanner.assert_safe(
            "This first snippet is example only.\n"
            f"Production credential accidentally pasted later: {value}"
        )


def test_scanner_allows_documentation_placeholders() -> None:
    scanner = SecretScanner()

    scanner.assert_safe("Authorization: Bearer ${TOKEN}")
    scanner.assert_safe("api_key=<API_KEY>")
    scanner.assert_safe("password=REDACTED")


def test_memory_rejects_secret_before_embedding_or_storage() -> None:
    embedding = CountingEmbedding()
    repository = NoopRepository()
    service = MemoryService(
        repository=repository,
        embedding=embedding,
        collection="episodic",
    )

    with pytest.raises(SensitiveDataError):
        service.store(
            content="Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
            session_id="session-1",
            event_time=datetime(2026, 9, 4, tzinfo=UTC),
        )

    assert embedding.calls == 0
    assert repository.upserts == 0
