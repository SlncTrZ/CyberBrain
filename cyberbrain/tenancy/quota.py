# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .models import _DIMENSION_ORDER, IdentityDimension, IdentityScope
from .normalization import normalize_identifier


class QuotaResource(StrEnum):
    REQUESTS = "requests"
    WRITES = "writes"
    RECALL_LIMIT = "recall_limit"
    DREAM_ENQUEUE = "dream_enqueue"
    BACKGROUND_REASONING = "background_reasoning"


@dataclass(frozen=True, slots=True)
class QuotaLimit:
    resource: QuotaResource
    amount: int
    window_seconds: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource", QuotaResource(self.resource))
        if type(self.amount) is not int:
            raise TypeError("quota amount must be an integer")
        if self.amount < 1:
            raise ValueError("quota amount must be positive")
        if self.window_seconds is not None and type(self.window_seconds) is not int:
            raise TypeError("quota window_seconds must be an integer")
        if self.window_seconds is not None and self.window_seconds < 1:
            raise ValueError("quota window_seconds must be positive")
        if (
            self.resource
            in {
                QuotaResource.REQUESTS,
                QuotaResource.WRITES,
                QuotaResource.DREAM_ENQUEUE,
                QuotaResource.BACKGROUND_REASONING,
            }
            and self.window_seconds is None
        ):
            raise ValueError(f"quota window_seconds required for {self.resource.value}")
        if self.resource is QuotaResource.RECALL_LIMIT and self.window_seconds is not None:
            raise ValueError("recall_limit quota must not define window_seconds")


@dataclass(frozen=True, slots=True)
class QuotaPolicy:
    limits: tuple[QuotaLimit, ...] = ()

    def __post_init__(self) -> None:
        resources = [limit.resource for limit in self.limits]
        if len(resources) != len(set(resources)):
            raise ValueError("quota policy must not contain duplicate resources")

    def limit_for(self, resource: QuotaResource) -> QuotaLimit | None:
        resource = QuotaResource(resource)
        for limit in self.limits:
            if limit.resource == resource:
                return limit
        return None


@dataclass(frozen=True, slots=True)
class QuotaScopeKey:
    values: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.values, tuple):
            raise TypeError("quota scope key values must be a tuple")
        if not self.values:
            raise ValueError("quota scope key must contain at least one identity dimension")

        normalized: dict[IdentityDimension, str] = {}
        for pair in self.values:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise TypeError("quota scope key entries must be (dimension, value) tuples")
            raw_dimension, raw_value = pair
            dimension = IdentityDimension(raw_dimension)
            if dimension in normalized:
                raise ValueError(f"duplicate quota key dimension: {dimension.value}")
            normalized[dimension] = normalize_identifier(raw_value)

        object.__setattr__(
            self,
            "values",
            tuple(
                (dimension.value, normalized[dimension])
                for dimension in _DIMENSION_ORDER
                if dimension in normalized
            ),
        )

    def as_dict(self) -> dict[str, str]:
        return dict(self.values)


def derive_quota_scope_key(
    scope: IdentityScope,
    *,
    dimensions: frozenset[IdentityDimension],
) -> QuotaScopeKey:
    required = frozenset(IdentityDimension(value) for value in dimensions)
    if not required:
        raise ValueError("quota key dimensions must not be empty")

    values: list[tuple[str, str]] = []
    for dimension in _DIMENSION_ORDER:
        if dimension not in required:
            continue
        scoped = scope.values(dimension)
        if len(scoped) != 1:
            raise ValueError(f"quota key requires exactly one {dimension.value}")
        values.append((dimension.value, next(iter(scoped))))
    return QuotaScopeKey(tuple(values))


@dataclass(frozen=True, slots=True)
class QuotaDecisionInput:
    resource: QuotaResource
    scope_key: QuotaScopeKey
    used: int
    requested: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource", QuotaResource(self.resource))
        if not isinstance(self.scope_key, QuotaScopeKey):
            raise TypeError("quota decision scope_key must be a QuotaScopeKey")
        if type(self.used) is not int:
            raise TypeError("quota used amount must be an integer")
        if self.used < 0:
            raise ValueError("quota used amount must not be negative")
        if type(self.requested) is not int:
            raise TypeError("quota requested amount must be an integer")
        if self.requested < 1:
            raise ValueError("quota requested amount must be positive")


@dataclass(frozen=True, slots=True)
class QuotaDecision:
    allow: bool
    reason_code: str
    limit: QuotaLimit | None
    remaining: int | None


def evaluate_quota(policy: QuotaPolicy, decision_input: QuotaDecisionInput) -> QuotaDecision:
    limit = policy.limit_for(decision_input.resource)
    if limit is None:
        return QuotaDecision(True, "QUOTA_NOT_CONFIGURED", None, None)

    projected = decision_input.used + decision_input.requested
    if projected > limit.amount:
        return QuotaDecision(
            False,
            "QUOTA_EXCEEDED",
            limit,
            max(limit.amount - decision_input.used, 0),
        )
    return QuotaDecision(True, "QUOTA_ALLOWED", limit, limit.amount - projected)
