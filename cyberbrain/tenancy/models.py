# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .normalization import normalize_identifier


class IdentityDimension(StrEnum):
    TENANT = "tenant"
    USER = "user"
    AGENT = "agent"
    PROJECT = "project"
    SESSION = "session"


_DIMENSION_ORDER = (
    IdentityDimension.TENANT,
    IdentityDimension.USER,
    IdentityDimension.AGENT,
    IdentityDimension.PROJECT,
    IdentityDimension.SESSION,
)


class OperationClass(StrEnum):
    READ = "read"
    WRITE = "write"
    ADMIN_REVIEW = "admin_review"
    BACKGROUND_REASONING = "background_reasoning"


def _normalize_values(
    values: frozenset[str] | set[str] | tuple[str, ...] | list[str] | None,
) -> frozenset[str]:
    if values is None:
        return frozenset()
    normalized = frozenset(normalize_identifier(value) for value in values)
    if not normalized:
        return frozenset()
    return normalized


@dataclass(frozen=True, slots=True)
class IdentityScope:
    tenant: frozenset[str] = frozenset()
    user: frozenset[str] = frozenset()
    agent: frozenset[str] = frozenset()
    project: frozenset[str] = frozenset()
    session: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for dimension in _DIMENSION_ORDER:
            raw = getattr(self, dimension.value)
            object.__setattr__(self, dimension.value, _normalize_values(raw))

    @classmethod
    def from_values(
        cls,
        *,
        tenant=None,
        user=None,
        agent=None,
        project=None,
        session=None,
    ) -> IdentityScope:
        def as_values(value):
            if value is None:
                return None
            if isinstance(value, str):
                return (value,)
            return value

        return cls(
            tenant=as_values(tenant),
            user=as_values(user),
            agent=as_values(agent),
            project=as_values(project),
            session=as_values(session),
        )

    def values(self, dimension: IdentityDimension) -> frozenset[str]:
        return getattr(self, dimension.value)

    def as_dict(self) -> dict[str, tuple[str, ...]]:
        return {
            dimension.value: tuple(sorted(self.values(dimension)))
            for dimension in _DIMENSION_ORDER
            if self.values(dimension)
        }


@dataclass(frozen=True, slots=True)
class ScopeRequirements:
    required_dimensions: frozenset[IdentityDimension] = frozenset()

    def __post_init__(self) -> None:
        normalized = frozenset(IdentityDimension(value) for value in self.required_dimensions)
        object.__setattr__(self, "required_dimensions", normalized)


@dataclass(frozen=True, slots=True)
class AuthorityGrant:
    scope: IdentityScope
    operations: frozenset[OperationClass]

    def __post_init__(self) -> None:
        normalized = frozenset(OperationClass(value) for value in self.operations)
        if not normalized:
            raise ValueError("authority grant must allow at least one operation")
        object.__setattr__(self, "operations", normalized)


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    allow: bool
    reason_code: str
    effective_scope: IdentityScope | None = None
