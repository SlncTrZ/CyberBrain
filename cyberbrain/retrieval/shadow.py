# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from threading import Lock, Thread
from time import monotonic
from typing import Any

from cyberbrain.core.metrics import MetricsRegistry
from cyberbrain.storage.base import PointRepository

from .lexical import BM25Corpus, BM25Document
from .literal import literal_heavy_query

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _ShadowRecord:
    id: str
    payload: dict[str, Any]

    @property
    def content(self) -> str:
        return str(self.payload.get("content") or "")


class KnowledgeLiteralShadowObserver:
    """Non-blocking lexical shadow observer for literal-heavy Knowledge queries.

    Caller-visible results remain untouched. The observer keeps a bounded, periodically refreshed
    in-process cache of active Knowledge payloads, applies the same explicit equality filters used
    by vector search, and records only numeric metrics plus content-free query/ID fingerprints.
    """

    def __init__(
        self,
        *,
        repository: PointRepository,
        collection: str,
        metrics: MetricsRegistry,
        cache_ttl_seconds: float = 300.0,
        max_records: int = 5_000,
    ) -> None:
        if cache_ttl_seconds <= 0:
            raise ValueError("cache_ttl_seconds must be > 0")
        if max_records < 1:
            raise ValueError("max_records must be > 0")
        self._repository = repository
        self._collection = collection
        self._metrics = metrics
        self._cache_ttl_seconds = cache_ttl_seconds
        self._max_records = max_records
        self._cache_lock = Lock()
        self._worker_lock = Lock()
        self._cache: tuple[_ShadowRecord, ...] = ()
        self._corpus: BM25Corpus | None = None
        self._cache_loaded_at = 0.0

    def submit(
        self,
        *,
        query: str,
        vector_rows: list[dict[str, Any]],
        filters: dict[str, Any],
        limit: int,
    ) -> None:
        if not literal_heavy_query(query):
            return
        self._metrics.increment("knowledge_literal_shadow_detected_total")

        if filters.get("status", "active") != "active":
            self._metrics.increment("knowledge_literal_shadow_skipped_status_total")
            return
        if not self._worker_lock.acquire(blocking=False):
            self._metrics.increment("knowledge_literal_shadow_skipped_busy_total")
            return

        copied_rows = [dict(row) for row in vector_rows]
        copied_filters = dict(filters)
        worker = Thread(
            target=self._run_worker,
            kwargs={
                "query": query,
                "vector_rows": copied_rows,
                "filters": copied_filters,
                "limit": limit,
            },
            name="cyberbrain-literal-shadow",
            daemon=True,
        )
        try:
            worker.start()
        except Exception:
            self._worker_lock.release()
            self._metrics.increment("knowledge_literal_shadow_failures_total")
            _LOGGER.exception("literal shadow worker failed to start")

    def _run_worker(
        self,
        *,
        query: str,
        vector_rows: list[dict[str, Any]],
        filters: dict[str, Any],
        limit: int,
    ) -> None:
        try:
            self.observe(query=query, vector_rows=vector_rows, filters=filters, limit=limit)
        except Exception:
            self._metrics.increment("knowledge_literal_shadow_failures_total")
            _LOGGER.exception("literal shadow observation failed")
        finally:
            self._worker_lock.release()

    def observe(
        self,
        *,
        query: str,
        vector_rows: list[dict[str, Any]],
        filters: dict[str, Any],
        limit: int,
    ) -> list[str]:
        """Run one shadow observation synchronously; intended for tests and the worker."""

        started = monotonic()
        records, corpus = self._eligible_records(filters)
        if not records:
            self._metrics.increment("knowledge_literal_shadow_empty_total")
            self._metrics.increment("knowledge_literal_shadow_evaluated_total")
            self._metrics.observe("knowledge_literal_shadow_seconds", monotonic() - started)
            return []

        scoring_started = monotonic()
        ranked = corpus.score(query, document_ids=[record.id for record in records])
        self._metrics.observe(
            "knowledge_literal_shadow_scoring_seconds", monotonic() - scoring_started
        )
        lexical_ids = [record_id for record_id, _score in ranked]
        top_k = max(1, min(limit, 50))
        vector_ids = [str(row.get("id") or "") for row in vector_rows if row.get("id")]
        vector_top = vector_ids[:top_k]
        lexical_top = lexical_ids[:top_k]

        self._metrics.increment("knowledge_literal_shadow_evaluated_total")
        if vector_top and lexical_top and vector_top[0] == lexical_top[0]:
            self._metrics.increment("knowledge_literal_shadow_top1_agreement_total")
        elif vector_top and lexical_top:
            self._metrics.increment("knowledge_literal_shadow_top1_changed_total")

        overlap_denominator = max(1, min(top_k, max(len(vector_top), len(lexical_top))))
        overlap = len(set(vector_top) & set(lexical_top)) / overlap_denominator
        self._metrics.observe("knowledge_literal_shadow_overlap_at_k", overlap)
        self._metrics.observe(
            "knowledge_literal_shadow_vector_tokens_at_k",
            float(self._token_estimate(vector_rows[:top_k])),
        )
        payload_by_id = {record.id: record.payload for record in records}
        ordered_lexical_payloads = [payload_by_id[record_id] for record_id in lexical_top]
        self._metrics.observe(
            "knowledge_literal_shadow_lexical_tokens_at_k",
            float(self._token_estimate(ordered_lexical_payloads)),
        )
        if vector_top:
            try:
                lexical_rank = lexical_ids.index(vector_top[0]) + 1
            except ValueError:
                lexical_rank = len(lexical_ids) + 1
            self._metrics.observe(
                "knowledge_literal_shadow_vector_top1_lexical_rank",
                float(lexical_rank),
            )

        self._metrics.observe("knowledge_literal_shadow_seconds", monotonic() - started)
        query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
        _LOGGER.info(
            "literal shadow query=%s vector_top=%s lexical_top=%s overlap=%.3f",
            query_hash,
            ",".join(vector_top),
            ",".join(lexical_top),
            overlap,
        )
        return lexical_ids

    def _eligible_records(
        self, filters: dict[str, Any]
    ) -> tuple[tuple[_ShadowRecord, ...], BM25Corpus]:
        records, corpus = self._records()
        active_filters = {
            key: value for key, value in filters.items() if value is not None
        }
        if not active_filters:
            return records, corpus
        return (
            tuple(
                record
                for record in records
                if all(
                    self._matches_filter(record.payload, key, value)
                    for key, value in active_filters.items()
                )
            ),
            corpus,
        )

    @staticmethod
    def _matches_filter(payload: dict[str, Any], key: str, value: Any) -> bool:
        if key in {"record_class", "ordinary_recall"} and key not in payload:
            return True
        return payload.get(key) == value

    def _records(self) -> tuple[tuple[_ShadowRecord, ...], BM25Corpus]:
        now = monotonic()
        with self._cache_lock:
            if (
                self._corpus is not None
                and now - self._cache_loaded_at < self._cache_ttl_seconds
            ):
                return self._cache, self._corpus

            started = monotonic()
            points = self._repository.scroll(
                self._collection,
                qdrant_filter={
                    "must": [{"key": "status", "match": {"value": "active"}}]
                },
                limit=self._max_records + 1,
            )
            if len(points) > self._max_records:
                self._metrics.increment("knowledge_literal_shadow_cache_too_large_total")
                raise RuntimeError("literal shadow cache exceeded configured max_records")

            cache = tuple(
                _ShadowRecord(
                    id=str(point.get("id") or ""),
                    payload=dict(point.get("payload") or {}),
                )
                for point in points
                if point.get("id")
            )
            corpus = BM25Corpus(
                [BM25Document(record.id, record.content) for record in cache]
            )
            self._cache = cache
            self._corpus = corpus
            self._cache_loaded_at = now
            self._metrics.increment("knowledge_literal_shadow_cache_refresh_total")
            self._metrics.observe(
                "knowledge_literal_shadow_cache_refresh_seconds", monotonic() - started
            )
            self._metrics.observe(
                "knowledge_literal_shadow_cache_records", float(len(cache))
            )
            return cache, corpus

    @staticmethod
    def _token_estimate(rows: list[dict[str, Any]]) -> int:
        total = 0
        for row in rows:
            summary = str(row.get("summary") or "").strip()
            text = summary if summary else str(row.get("content") or "")[:1200]
            total += (len(text) + 3) // 4
        return total
