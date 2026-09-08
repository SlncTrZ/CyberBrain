# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
from time import perf_counter

from cyberbrain.tenancy import (
    AuthorityGrant,
    IdentityDimension,
    IdentityScope,
    OperationClass,
    ScopeAuthorizationPolicy,
    ScopeRequirements,
    build_storage_filter,
)


def run(iterations: int = 100000) -> dict[str, float | int]:
    grant = AuthorityGrant(
        scope=IdentityScope.from_values(
            tenant="tenant-a",
            user="user-a",
            agent="agent-a",
            project=("alpha", "beta"),
        ),
        operations=frozenset({OperationClass.READ, OperationClass.WRITE}),
    )
    request = IdentityScope.from_values(project="alpha")
    requirements = ScopeRequirements(
        frozenset({IdentityDimension.TENANT, IdentityDimension.PROJECT})
    )

    started = perf_counter()
    allowed = 0
    filters = 0
    for _ in range(iterations):
        decision = ScopeAuthorizationPolicy.decide(
            grant,
            requested_scope=request,
            operation=OperationClass.READ,
            requirements=requirements,
        )
        if decision.allow and decision.effective_scope is not None:
            allowed += 1
            build_storage_filter(
                decision.effective_scope,
                required_dimensions=requirements.required_dimensions,
            )
            filters += 1
    elapsed = perf_counter() - started
    return {
        "iterations": iterations,
        "allowed": allowed,
        "filters_built": filters,
        "total_seconds": round(elapsed, 6),
        "microseconds_per_decision_and_filter": round(elapsed * 1_000_000 / iterations, 3),
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
