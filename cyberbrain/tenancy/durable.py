# SPDX-License-Identifier: MPL-2.0
"""Credential-free, validated authority snapshots for durable internal jobs."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager

from cyberbrain.core.errors import ConfigurationError

from .auth import (
    CallerAuthority,
    DeploymentMode,
    authority_for_authenticated_scope,
    bind_authority,
    current_authority,
)
from .models import IdentityScope, OperationClass


def authority_snapshot(authority: CallerAuthority | None = None) -> str:
    caller = authority or current_authority()
    if caller is None:
        caller = authority_for_authenticated_scope(
            DeploymentMode.SINGLE_OWNER, scope=IdentityScope(),
            operations=frozenset(OperationClass),
        )
    return json.dumps({
        "schema": 1,
        "mode": caller.deployment_mode.value,
        "scope": caller.grant.scope.as_dict(),
        "operations": sorted(op.value for op in caller.grant.operations),
    }, sort_keys=True, separators=(",", ":"))


def restore_authority(snapshot: str) -> CallerAuthority:
    try:
        value = json.loads(snapshot)
        if (
            not isinstance(value, dict)
            or set(value) != {"schema", "mode", "scope", "operations"}
            or type(value["schema"]) is not int or value["schema"] != 1
            or not isinstance(value["scope"], dict)
            or not isinstance(value["operations"], list)
        ):
            raise ValueError("unknown authority snapshot")
        return authority_for_authenticated_scope(
            value["mode"], scope=IdentityScope.from_values(**value["scope"]),
            operations=frozenset(OperationClass(op) for op in value["operations"]),
        )
    except (TypeError, ValueError, KeyError):
        raise ConfigurationError("invalid durable authority snapshot") from None


@contextmanager
def bind_job_authority(snapshot: str | None) -> Iterator[None]:
    # Only pre-snapshot jobs may use the explicit legacy single-owner boundary.
    legacy = authority_for_authenticated_scope(
        DeploymentMode.SINGLE_OWNER, scope=IdentityScope(),
        operations=frozenset(OperationClass),
    )
    authority = restore_authority(snapshot) if snapshot is not None else legacy
    with bind_authority(authority):
        yield


def identity_key(snapshot: str) -> str:
    return json.dumps(restore_authority(snapshot).grant.scope.as_dict(),
                      sort_keys=True, separators=(",", ":"))


def snapshot_visible(snapshot: str | None) -> bool:
    caller = current_authority()
    if caller is None or not caller.grant.scope.as_dict():
        return True
    if snapshot is None:
        return False
    persisted = restore_authority(snapshot).grant.scope
    for dimension, allowed in caller.grant.scope.as_dict().items():
        actual = getattr(persisted, dimension)
        if not actual or not actual.issubset(allowed):
            return False
    return True


def snapshot_sql_filter(column: str) -> tuple[str, list[str]]:
    """Use only internally supplied column names; bind every identity value."""
    if column not in {"authority_json", "a.authority_json"}:
        raise ValueError("unsupported snapshot column")
    caller = current_authority()
    if caller is None:
        return "", []
    clauses = []
    parameters = []
    for dimension, allowed in caller.grant.scope.as_dict().items():
        placeholders = ",".join("?" for _ in allowed)
        path = "$.scope." + dimension
        clauses.append(
            f"json_array_length({column}, '{path}') > 0 AND NOT EXISTS ("
            f"SELECT 1 FROM json_each({column}, '{path}') AS scoped "
            f"WHERE scoped.value NOT IN ({placeholders}))"
        )
        parameters.extend(allowed)
    return (" AND " + " AND ".join(clauses) if clauses else ""), parameters
