# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from .models import (
    _DIMENSION_ORDER,
    AuthorityGrant,
    AuthorizationDecision,
    IdentityScope,
    OperationClass,
    ScopeRequirements,
)


class ScopeAuthorizationPolicy:
    """Transport-neutral fail-closed authority narrowing policy."""

    @staticmethod
    def decide(
        grant: AuthorityGrant,
        *,
        requested_scope: IdentityScope,
        operation: OperationClass,
        requirements: ScopeRequirements | None = None,
    ) -> AuthorizationDecision:
        operation = OperationClass(operation)
        requirements = requirements or ScopeRequirements()
        if operation not in grant.operations:
            return AuthorizationDecision(False, "OPERATION_NOT_ALLOWED")

        effective: dict[str, frozenset[str]] = {}
        for dimension in _DIMENSION_ORDER:
            allowed_values = grant.scope.values(dimension)
            requested_values = requested_scope.values(dimension)

            if requested_values:
                if not allowed_values:
                    return AuthorizationDecision(False, f"SCOPE_WIDENING_{dimension.value.upper()}")
                if not requested_values.issubset(allowed_values):
                    return AuthorizationDecision(False, f"SCOPE_WIDENING_{dimension.value.upper()}")
                effective[dimension.value] = requested_values
            else:
                effective[dimension.value] = allowed_values

        effective_scope = IdentityScope(**effective)
        for dimension in requirements.required_dimensions:
            if not effective_scope.values(dimension):
                return AuthorizationDecision(
                    False, f"REQUIRED_SCOPE_MISSING_{dimension.value.upper()}"
                )

        return AuthorizationDecision(True, "SCOPE_ALLOWED", effective_scope)
