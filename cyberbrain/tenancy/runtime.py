# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cyberbrain.core.errors import ConfigurationError

from .auth import CallerAuthority, current_authority
from .enforcement import EnforcementPlan, TenancyOperation, plan_enforcement
from .models import IdentityScope
from .normalization import normalize_identifier

IDENTITY_FIELDS = ("tenant", "user", "agent", "project", "session_id")


def enforce_operation(
    operation: TenancyOperation,
    selectors: Mapping[str, Any] | None = None,
    *,
    authority: CallerAuthority | None = None,
) -> EnforcementPlan | None:
    """Use bound authority; an unbound call is an internal service invocation.

    Empty optional dimensions are contextual selectors inside the required
    principal boundary, not a source of authenticated identity. Constrained dimensions always narrow
    through the existing subset policy.
    """
    caller = authority or current_authority()
    if caller is None:
        return None
    requested = {}
    for field in IDENTITY_FIELDS:
        value = (selectors or {}).get(field)
        if value is None:
            continue
        dimension = "session" if field == "session_id" else field
        normalized = normalize_identifier(value)
        if getattr(caller.grant.scope, dimension):
            requested[dimension] = normalized

    plan = plan_enforcement(
        caller,
        operation=operation,
        requested_scope=IdentityScope.from_values(**requested),
    )
    if not plan.allow:
        raise ConfigurationError("caller scope does not allow this operation")
    return plan


def scoped_values(
    values: Mapping[str, Any],
    *,
    operation: TenancyOperation,
    authority: CallerAuthority | None = None,
) -> dict[str, Any]:
    result = dict(values)
    plan = enforce_operation(operation, result, authority=authority)
    if plan is not None and plan.write_attribution is not None:
        for field, value in plan.write_attribution.values:
            result["session_id" if field == "session" else field] = value
    if plan is not None:
        for field in IDENTITY_FIELDS:
            if result.get(field) is not None:
                result[field] = normalize_identifier(result[field])
    return result


def scope_conditions(plan: EnforcementPlan | None) -> list[dict]:
    if plan is None or plan.storage_filter is None:
        return []
    from cyberbrain.storage.scoping import storage_filter_to_repository_filter

    query = storage_filter_to_repository_filter(
        plan.storage_filter, field_aliases={"session": "session_id"},
    )
    return (query or {}).get("must", [])
