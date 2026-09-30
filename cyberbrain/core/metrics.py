# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from threading import Lock

from cyberbrain.tenancy.auth import current_authority
from cyberbrain.tenancy.models import IdentityScope


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
        self._timings: dict[str, MetricSample] = {}
        self._scoped: dict[str, tuple[dict[str, int], dict[str, MetricSample]]] = {}

    @staticmethod
    def _scope_key(scope: IdentityScope | None) -> str | None:
        if scope is None:
            return None
        values = scope.as_dict()
        selected = {key: values[key] for key in ("tenant", "user") if key in values}
        if not selected and "agent" in values:
            selected = {"agent": values["agent"]}
        if not selected:
            return None
        return hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest()

    def _current_metrics(self):
        caller = current_authority()
        key = self._scope_key(caller.grant.scope if caller else None)
        if key is None:
            return None
        if key not in self._scoped:
            if len(self._scoped) >= 2048:
                name = "metrics_scope_capacity_skips_total"
                self._counters[name] = self._counters.get(name, 0) + 1
                return None
            self._scoped[key] = ({}, {})
        return self._scoped[key]

    def increment(self, name: str, amount: int = 1) -> None:
        if amount < 0:
            raise ValueError("metric increment must be >= 0")
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount
            scoped = self._current_metrics()
            if scoped is not None:
                scoped[0][name] = scoped[0].get(name, 0) + amount

    def observe(self, name: str, value: float) -> None:
        if not math.isfinite(value) or value < 0:
            raise ValueError("metric observation must be finite and >= 0")
        with self._lock:
            registries = [self._timings]
            scoped = self._current_metrics()
            if scoped is not None:
                registries.append(scoped[1])
            for registry in registries:
                prior = registry.get(name, MetricSample(0, 0.0, None, None))
                registry[name] = MetricSample(
                    prior.count + 1, prior.total + value,
                    min(prior.minimum, value) if prior.minimum is not None else value,
                    max(prior.maximum, value) if prior.maximum is not None else value,
                )

    def snapshot(self, *, scope: IdentityScope | None = None) -> dict[str, object]:
        with self._lock:
            key = self._scope_key(scope)
            selected = self._scoped.get(key, ({}, {})) if key is not None else (
                self._counters, self._timings,
            )
            counters = dict(selected[0])
            timings = dict(selected[1])
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
