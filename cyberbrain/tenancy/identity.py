# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass

from .auth import CallerAuthority, DeploymentMode, authority_for_authenticated_scope
from .models import IdentityScope, OperationClass


@dataclass(frozen=True, slots=True, init=False)
class TrustedIdentityEvidence:
    """Identity evidence produced by a trusted authentication boundary.

    The tenancy domain intentionally accepts only this typed seam for authenticated
    identity conversion. Transport payload mappings and strings are not accepted as
    substitutes for authenticated identity evidence.
    """

    scope: IdentityScope
    authentication_source: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:  # pragma: no cover
        raise TypeError(
            "TrustedIdentityEvidence must be created by from_authentication_boundary()"
        )

    @classmethod
    def from_authentication_boundary(
        cls,
        *,
        scope: IdentityScope,
        authentication_source: str,
    ) -> TrustedIdentityEvidence:
        if not isinstance(scope, IdentityScope):
            raise TypeError("trusted identity scope must be an IdentityScope")
        source = authentication_source.strip()
        if not source:
            raise ValueError("authentication_source must not be empty")

        instance = object.__new__(cls)
        object.__setattr__(instance, "scope", scope)
        object.__setattr__(instance, "authentication_source", source)
        return instance

    def to_authority(
        self,
        mode: DeploymentMode | str,
        *,
        operations: frozenset[OperationClass]
        | set[OperationClass]
        | tuple[OperationClass, ...],
    ) -> CallerAuthority:
        return authority_for_authenticated_scope(
            mode,
            scope=self.scope,
            operations=operations,
        )


def authority_from_trusted_identity(
    mode: DeploymentMode | str,
    *,
    identity: TrustedIdentityEvidence,
    operations: frozenset[OperationClass]
    | set[OperationClass]
    | tuple[OperationClass, ...],
) -> CallerAuthority:
    if not isinstance(identity, TrustedIdentityEvidence):
        raise TypeError("trusted authenticated identity evidence is required")
    return identity.to_authority(mode, operations=operations)
