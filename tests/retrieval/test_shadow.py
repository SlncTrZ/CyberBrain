# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from threading import Event
from time import monotonic, sleep
from typing import Any

import pytest

import cyberbrain.retrieval.lexical as lexical_module
from cyberbrain.core.metrics import MetricsRegistry
from cyberbrain.retrieval.literal import literal_heavy_query
from cyberbrain.retrieval.shadow import KnowledgeLiteralShadowObserver


class ShadowRepository:
    def __init__(self, points: list[dict[str, Any]]) -> None:
        self.points = points
        self.scroll_calls = 0
        self.last_filter: dict[str, Any] | None = None

    def scroll(self, collection: str, *, qdrant_filter=None, limit: int = 100):  # noqa: ANN001
        self.scroll_calls += 1
        self.last_filter = qdrant_filter
        return self.points[:limit]


class BlockingShadowRepository(ShadowRepository):
    def __init__(self, points: list[dict[str, Any]]) -> None:
        super().__init__(points)
        self.started = Event()
        self.release = Event()

    def scroll(self, collection: str, *, qdrant_filter=None, limit: int = 100):  # noqa: ANN001
        self.started.set()
        self.release.wait(timeout=2)
        return super().scroll(collection, qdrant_filter=qdrant_filter, limit=limit)


def _point(record_id: str, *, project: str | None, content: str) -> dict[str, Any]:
    return {
        "id": record_id,
        "payload": {
            "status": "active",
            "project": project,
            "content": content,
        },
    }


def test_literal_detector_is_shared_with_runtime_policy() -> None:
    assert literal_heavy_query("deploy commit c5a8ed9") is True
    assert literal_heavy_query("qwen3:0.6b with 5/5 clean stops") is True
    assert literal_heavy_query("why did provider discovery remain out of sync") is False


def test_shadow_applies_same_explicit_filters_before_bm25() -> None:
    repo = ShadowRepository(
        [
            _point("target", project="alpha", content="release abc1234 exact fingerprint"),
            _point("outside", project=None, content="release abc1234 exact fingerprint"),
            _point("other", project="beta", content="release abc1234 exact fingerprint"),
            {
                "id": "missing-status",
                "payload": {
                    "project": "alpha",
                    "content": "release abc1234 exact fingerprint",
                },
            },
        ]
    )
    metrics = MetricsRegistry()
    observer = KnowledgeLiteralShadowObserver(
        repository=repo,
        collection="knowledge",
        metrics=metrics,
    )

    lexical_ids = observer.observe(
        query="release abc1234",
        vector_rows=[{"id": "target", "content": "release abc1234 exact fingerprint"}],
        filters={"status": "active", "project": "alpha"},
        limit=5,
    )

    assert lexical_ids == ["target"]
    assert repo.last_filter == {
        "must": [{"key": "status", "match": {"value": "active"}}]
    }
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["knowledge_literal_shadow_evaluated_total"] == 1
    assert snapshot["counters"]["knowledge_literal_shadow_top1_agreement_total"] == 1
    assert snapshot["timings"]["knowledge_literal_shadow_overlap_at_k"]["avg"] == 1.0


def test_shadow_cache_is_reused_within_ttl() -> None:
    repo = ShadowRepository([_point("target", project=None, content="commit abc1234")])
    observer = KnowledgeLiteralShadowObserver(
        repository=repo,
        collection="knowledge",
        metrics=MetricsRegistry(),
        cache_ttl_seconds=60,
    )

    for _ in range(2):
        observer.observe(
            query="commit abc1234",
            vector_rows=[{"id": "target", "content": "commit abc1234"}],
            filters={"status": "active"},
            limit=5,
        )

    assert repo.scroll_calls == 1


def test_shadow_cache_reuses_pre_tokenized_bm25_corpus(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = ShadowRepository(
        [
            _point("target", project=None, content="commit abc1234 exact fingerprint"),
            _point("other", project=None, content="generic release notes"),
        ]
    )
    observer = KnowledgeLiteralShadowObserver(
        repository=repo,
        collection="knowledge",
        metrics=MetricsRegistry(),
        cache_ttl_seconds=60,
    )
    original_tokenize = lexical_module.tokenize
    calls: list[str] = []

    def counting_tokenize(text: str) -> tuple[str, ...]:
        calls.append(text)
        return original_tokenize(text)

    monkeypatch.setattr(lexical_module, "tokenize", counting_tokenize)

    for _ in range(2):
        observer.observe(
            query="commit abc1234",
            vector_rows=[{"id": "target", "content": "commit abc1234 exact fingerprint"}],
            filters={"status": "active"},
            limit=5,
        )

    assert repo.scroll_calls == 1
    assert calls.count("commit abc1234 exact fingerprint") == 1
    assert calls.count("generic release notes") == 1
    assert calls.count("commit abc1234") == 2


def test_shadow_fails_closed_if_corpus_exceeds_bound() -> None:
    repo = ShadowRepository(
        [
            _point("one", project=None, content="commit abc1234"),
            _point("two", project=None, content="commit abc1234"),
        ]
    )
    observer = KnowledgeLiteralShadowObserver(
        repository=repo,
        collection="knowledge",
        metrics=MetricsRegistry(),
        max_records=1,
    )

    with pytest.raises(RuntimeError, match="max_records"):
        observer.observe(
            query="commit abc1234",
            vector_rows=[],
            filters={"status": "active"},
            limit=5,
        )


def test_submit_is_non_blocking_and_skips_when_worker_is_busy() -> None:
    repo = BlockingShadowRepository([_point("target", project=None, content="commit abc1234")])
    metrics = MetricsRegistry()
    observer = KnowledgeLiteralShadowObserver(
        repository=repo,
        collection="knowledge",
        metrics=metrics,
    )

    started = monotonic()
    observer.submit(
        query="commit abc1234",
        vector_rows=[{"id": "target", "content": "commit abc1234"}],
        filters={"status": "active"},
        limit=5,
    )
    elapsed = monotonic() - started
    assert elapsed < 0.2
    assert repo.started.wait(timeout=1)

    observer.submit(
        query="commit def5678",
        vector_rows=[],
        filters={"status": "active"},
        limit=5,
    )
    repo.release.set()

    deadline = monotonic() + 2
    while monotonic() < deadline:
        counters = metrics.snapshot()["counters"]
        if counters.get("knowledge_literal_shadow_evaluated_total") == 1:
            break
        sleep(0.01)

    counters = metrics.snapshot()["counters"]
    assert counters["knowledge_literal_shadow_detected_total"] == 2
    assert counters["knowledge_literal_shadow_skipped_busy_total"] == 1
    assert counters["knowledge_literal_shadow_evaluated_total"] == 1


def test_submit_skips_non_active_status_without_reading_corpus() -> None:
    repo = ShadowRepository([_point("target", project=None, content="commit abc1234")])
    metrics = MetricsRegistry()
    observer = KnowledgeLiteralShadowObserver(
        repository=repo,
        collection="knowledge",
        metrics=metrics,
    )

    observer.submit(
        query="commit abc1234",
        vector_rows=[],
        filters={"status": "superseded"},
        limit=5,
    )

    assert repo.scroll_calls == 0
    counters = metrics.snapshot()["counters"]
    assert counters["knowledge_literal_shadow_skipped_status_total"] == 1
