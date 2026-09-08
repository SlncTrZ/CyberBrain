# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass

from .models import _DIMENSION_ORDER, IdentityDimension, IdentityScope


@dataclass(frozen=True, slots=True)
class FilterCondition:
    field: str
    operator: str
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StorageFilter:
    conditions: tuple[FilterCondition, ...]

    def fields(self) -> frozenset[str]:
        return frozenset(condition.field for condition in self.conditions)


def build_storage_filter(
    effective_scope: IdentityScope,
    *,
    required_dimensions: frozenset[IdentityDimension] = frozenset(),
) -> StorageFilter:
    required = frozenset(IdentityDimension(value) for value in required_dimensions)
    conditions: list[FilterCondition] = []
    for dimension in _DIMENSION_ORDER:
        values = effective_scope.values(dimension)
        if dimension in required and not values:
            raise ValueError(f"required scope missing: {dimension.value}")
        if not values:
            continue
        sorted_values = tuple(sorted(values))
        operator = "eq" if len(sorted_values) == 1 else "in"
        conditions.append(FilterCondition(dimension.value, operator, sorted_values))

    fields = frozenset(condition.field for condition in conditions)
    missing = {dimension.value for dimension in required} - fields
    if missing:
        raise ValueError(f"storage filter omitted required dimensions: {sorted(missing)}")
    return StorageFilter(tuple(conditions))
