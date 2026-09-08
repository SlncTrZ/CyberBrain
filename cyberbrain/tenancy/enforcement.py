# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .attribution import WriteAttribution, build_write_attribution
from .auth import CallerAuthority, deployment_identity_profile
from .filters import StorageFilter, build_storage_filter
from .models import IdentityDimension, IdentityScope, OperationClass, ScopeRequirements
from .policy import ScopeAuthorizationPolicy


class TenancyOperation(StrEnum):
    KNOWLEDGE_SEARCH = "knowledge_search"
    MEMORY_SEARCH = "memory_search"
    KNOWLEDGE_GET = "knowledge_get"
    MEMORY_GET = "memory_get"
    KNOWLEDGE_TIMELINE = "knowledge_timeline"
    KNOWLEDGE_WRITE = "knowledge_write"
    MEMORY_WRITE = "memory_write"
    BACKGROUND_EVIDENCE_READ = "background_evidence_read"


@dataclass(frozen=True, slots=True)
class _OperationSpec:
    operation_class: OperationClass
    requires_storage_filter: bool
    requires_write_attribution: bool


_OPERATION_SPECS: dict[TenancyOperation, _OperationSpec] = {
    TenancyOperation.KNOWLEDGE_SEARCH: _OperationSpec(OperationClass.READ, True, False),
    TenancyOperation.MEMORY_SEARCH: _OperationSpec(OperationClass.READ, True, False),
    TenancyOperation.KNOWLEDGE_GET: _OperationSpec(OperationClass.READ, True, False),
    TenancyOperation.MEMORY_GET: _OperationSpec(OperationClass.READ, True, False),
    TenancyOperation.KNOWLEDGE_TIMELINE: _OperationSpec(OperationClass.READ, True, False),
    TenancyOperation.KNOWLEDGE_WRITE: _OperationSpec(OperationClass.WRITE, False, True),
    TenancyOperation.MEMORY_WRITE: _OperationSpec(OperationClass.WRITE, False, True),
    TenancyOperation.BACKGROUND_EVIDENCE_READ: _OperationSpec(
        OperationClass.BACKGROUND_REASONING,
        True,
        False,
    ),
}


@dataclass(frozen=True, slots=True)
class EnforcementPlan:
    operation: TenancyOperation
    operation_class: OperationClass
    allow: bool
    reason_code: str
    required_dimensions: frozenset[IdentityDimension]
    effective_scope: IdentityScope | None = None
    storage_filter: StorageFilter | None = None
    write_attribution: WriteAttribution | None = None


def plan_enforcement(
    authority: CallerAuthority,
    *,
    operation: TenancyOperation | str,
    requested_scope: IdentityScope | None = None,
) -> EnforcementPlan:
    """Produce a fail-closed authorization plan before any storage visibility."""

    operation = TenancyOperation(operation)
    spec = _OPERATION_SPECS[operation]
    profile = deployment_identity_profile(authority.deployment_mode)
    required_dimensions = profile.minimum_identity_dimensions
    decision = ScopeAuthorizationPolicy.decide(
        authority.grant,
        requested_scope=requested_scope or IdentityScope(),
        operation=spec.operation_class,
        requirements=ScopeRequirements(required_dimensions),
    )
    if not decision.allow or decision.effective_scope is None:
        return EnforcementPlan(
            operation=operation,
            operation_class=spec.operation_class,
            allow=False,
            reason_code=decision.reason_code,
            required_dimensions=required_dimensions,
        )

    effective_scope = decision.effective_scope
    storage_filter: StorageFilter | None = None
    write_attribution: WriteAttribution | None = None

    if spec.requires_storage_filter:
        try:
            storage_filter = build_storage_filter(
                effective_scope,
                required_dimensions=required_dimensions,
            )
        except ValueError:
            return EnforcementPlan(
                operation=operation,
                operation_class=spec.operation_class,
                allow=False,
                reason_code="REQUIRED_STORAGE_FILTER_UNAVAILABLE",
                required_dimensions=required_dimensions,
            )

        if not {dimension.value for dimension in required_dimensions}.issubset(
            storage_filter.fields()
        ):
            return EnforcementPlan(
                operation=operation,
                operation_class=spec.operation_class,
                allow=False,
                reason_code="REQUIRED_STORAGE_FILTER_UNAVAILABLE",
                required_dimensions=required_dimensions,
            )

    if spec.requires_write_attribution:
        try:
            write_attribution = build_write_attribution(
                effective_scope,
                required_dimensions=required_dimensions,
            )
        except ValueError:
            return EnforcementPlan(
                operation=operation,
                operation_class=spec.operation_class,
                allow=False,
                reason_code="WRITE_ATTRIBUTION_NOT_SINGLETON",
                required_dimensions=required_dimensions,
            )

    return EnforcementPlan(
        operation=operation,
        operation_class=spec.operation_class,
        allow=True,
        reason_code="ENFORCEMENT_ALLOWED",
        required_dimensions=required_dimensions,
        effective_scope=effective_scope,
        storage_filter=storage_filter,
        write_attribution=write_attribution,
    )
