# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from collections.abc import Mapping

from cyberbrain.tenancy import StorageFilter


def storage_filter_to_repository_filter(
    storage_filter: StorageFilter,
    *,
    include_fields: frozenset[str] | None = None,
    field_aliases: Mapping[str, str] | None = None,
) -> dict | None:
    aliases = field_aliases or {}
    conditions: list[dict] = []
    for condition in storage_filter.conditions:
        if include_fields is not None and condition.field not in include_fields:
            continue
        field = aliases.get(condition.field, condition.field)
        if condition.operator == "eq":
            match = {"value": condition.values[0]}
        elif condition.operator == "in":
            match = {"any": list(condition.values)}
        else:
            raise ValueError(f"unsupported storage filter operator: {condition.operator}")
        conditions.append({"key": field, "match": match})
    return {"must": conditions} if conditions else None
