# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class MetricSample:
    count: int
    total: float
    minimum: float | None
    maximum: float | None

    @property
    def average(self) -> float | None:
        return self.total / self.count if self.count else None


class MetricsRegistry:
    """Small in-process numeric metrics registry with no content-bearing labels."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, int] = {}
        self._timings: dict[str, list[float]] = {}

    def increment(self, name: str, amount: int = 1) -> None:
        if amount < 0:
            raise ValueError("metric increment must be >= 0")
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def observe(self, name: str, value: float) -> None:
        if value < 0:
            raise ValueError("metric observation must be >= 0")
        with self._lock:
            self._timings.setdefault(name, []).append(float(value))

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            counters = dict(self._counters)
            timings = {
                name: MetricSample(
                    count=len(values),
                    total=sum(values),
                    minimum=min(values) if values else None,
                    maximum=max(values) if values else None,
                )
                for name, values in self._timings.items()
            }
        return {
            "counters": counters,
            "timings": {
                name: {
                    "count": sample.count,
                    "total": sample.total,
                    "min": sample.minimum,
                    "max": sample.maximum,
                    "avg": sample.average,
                }
                for name, sample in timings.items()
            },
        }
