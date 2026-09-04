# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from time import monotonic

import httpx

from cyberbrain.core.errors import EmbeddingError
from cyberbrain.core.metrics import MetricsRegistry


class OllamaEmbeddingProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        dimension: int,
        version: str,
        timeout_seconds: float = 30.0,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimension = dimension
        self._version = version
        self._timeout_seconds = timeout_seconds
        self._metrics = metrics

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def version(self) -> str:
        return self._version

    def embed(self, text: str) -> list[float]:
        if not text.strip():
            raise EmbeddingError("cannot embed empty text")

        started = monotonic()
        try:
            response = httpx.post(
                f"{self._base_url}/api/embeddings",
                json={"model": self._model, "prompt": text[:8192]},
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            if self._metrics is not None:
                self._metrics.increment("embedding_requests_total")
                self._metrics.observe("embedding_request_seconds", monotonic() - started)
        except httpx.HTTPError as exc:
            if self._metrics is not None:
                self._metrics.increment("embedding_failures_total")
                self._metrics.observe("embedding_request_seconds", monotonic() - started)
            raise EmbeddingError(f"embedding request failed: {exc}") from exc

        vector = response.json().get("embedding")
        if not isinstance(vector, list):
            raise EmbeddingError("embedding response did not contain a vector")
        if len(vector) != self._dimension:
            raise EmbeddingError(
                f"embedding dimension mismatch: expected {self._dimension}, got {len(vector)}"
            )
        if not all(isinstance(value, int | float) for value in vector):
            raise EmbeddingError("embedding vector contains non-numeric values")

        return [float(value) for value in vector]
