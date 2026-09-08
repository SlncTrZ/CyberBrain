# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


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
        if self.amount < 1:
            raise ValueError("quota amount must be positive")
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
