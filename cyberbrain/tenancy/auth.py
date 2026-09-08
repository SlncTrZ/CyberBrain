# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum

from .models import AuthorityGrant, IdentityDimension, IdentityScope, OperationClass


class DeploymentMode(StrEnum):
    SINGLE_OWNER = "single_owner"
    AGENT_READY = "agent_ready"
    MULTI_USER = "multi_user"


@dataclass(frozen=True, slots=True)
class DeploymentIdentityProfile:
    mode: DeploymentMode
    minimum_identity_dimensions: frozenset[IdentityDimension]


@dataclass(frozen=True, slots=True)
class CallerAuthority:
    deployment_mode: DeploymentMode
    grant: AuthorityGrant


_DEPLOYMENT_PROFILES = {
    DeploymentMode.SINGLE_OWNER: DeploymentIdentityProfile(
        DeploymentMode.SINGLE_OWNER,
        frozenset(),
    ),
    DeploymentMode.AGENT_READY: DeploymentIdentityProfile(
        DeploymentMode.AGENT_READY,
        frozenset({IdentityDimension.AGENT}),
    ),
    DeploymentMode.MULTI_USER: DeploymentIdentityProfile(
        DeploymentMode.MULTI_USER,
        frozenset({IdentityDimension.TENANT, IdentityDimension.USER}),
    ),
}

_current_authority: ContextVar[CallerAuthority | None] = ContextVar(
    "cyberbrain_current_authority",
    default=None,
)


def deployment_identity_profile(mode: DeploymentMode | str) -> DeploymentIdentityProfile:
    return _DEPLOYMENT_PROFILES[DeploymentMode(mode)]


def authority_for_authenticated_scope(
    mode: DeploymentMode | str,
    *,
    scope: IdentityScope,
    operations: frozenset[OperationClass] | set[OperationClass] | tuple[OperationClass, ...],
) -> CallerAuthority:
    deployment_mode = DeploymentMode(mode)
    profile = deployment_identity_profile(deployment_mode)
    for dimension in profile.minimum_identity_dimensions:
        values = scope.values(dimension)
        if len(values) != 1:
            raise ValueError(
                f"authenticated caller requires exactly one {dimension.value} "
                f"for deployment mode {deployment_mode.value}"
            )
    return CallerAuthority(
        deployment_mode=deployment_mode,
        grant=AuthorityGrant(scope=scope, operations=frozenset(operations)),
    )


def current_authority() -> CallerAuthority | None:
    return _current_authority.get()


@contextmanager
def bind_authority(authority: CallerAuthority) -> Iterator[None]:
    token = _current_authority.set(authority)
    try:
        yield
    finally:
        _current_authority.reset(token)
