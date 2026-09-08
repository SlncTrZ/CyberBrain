# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass

from .models import _DIMENSION_ORDER, IdentityDimension, IdentityScope


@dataclass(frozen=True, slots=True)
class WriteAttribution:
    values: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, str]:
        return dict(self.values)


def build_write_attribution(
    effective_scope: IdentityScope,
    *,
    required_dimensions: frozenset[IdentityDimension] = frozenset(),
) -> WriteAttribution:
    required = frozenset(IdentityDimension(value) for value in required_dimensions)
    values: list[tuple[str, str]] = []
    for dimension in _DIMENSION_ORDER:
        scoped = effective_scope.values(dimension)
        if dimension in required and not scoped:
            raise ValueError(f"required write attribution missing: {dimension.value}")
        if not scoped:
            continue
        if len(scoped) != 1:
            raise ValueError(f"write attribution must resolve one value for {dimension.value}")
        values.append((dimension.value, next(iter(scoped))))
    return WriteAttribution(tuple(values))
