# SPDX-License-Identifier: MPL-2.0
"""Server-owned principal registry; persisted configuration contains no credentials."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from cyberbrain.core.errors import ConfigurationError

from .auth import CallerAuthority, DeploymentMode, authority_for_authenticated_scope
from .models import IdentityScope, OperationClass
from .normalization import normalize_identifier


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    principal_id: str
    authority: CallerAuthority
    identity_scope: IdentityScope
    credential_digest: bytes = field(repr=False)


class PrincipalRegistry:
    def __init__(self, principals: tuple[AuthenticatedPrincipal, ...]) -> None:
        if not principals or len(principals) > 1000:
            raise ConfigurationError("principal registry requires between 1 and 1000 principals")
        if len({p.principal_id for p in principals}) != len(principals):
            raise ConfigurationError("duplicate principal identifier")
        if len({p.credential_digest for p in principals}) != len(principals):
            raise ConfigurationError("credentials must identify exactly one principal")
        self._principals = principals

    @classmethod
    def load(cls, path: str | Path, *, mode: DeploymentMode) -> PrincipalRegistry:
        try:
            raw = Path(path).read_bytes()
            if len(raw) > 1_000_000:
                raise ValueError("registry exceeds bounded configuration size")
            value = json.loads(raw)
            if set(value) != {"schema", "principals"} or (
                type(value["schema"]) is not int or value["schema"] != 1
            ):
                raise ValueError("unknown registry schema")
            if not isinstance(value["principals"], list):
                raise ValueError("principals must be a list")
            principals = []
            for row in value["principals"]:
                if set(row) != {"principal_id", "credential_env", "scope", "operations"}:
                    raise ValueError("invalid principal entry")
                env_name = row["credential_env"]
                if not isinstance(env_name, str) or not re.fullmatch(
                    r"[A-Z][A-Z0-9_]{0,127}", env_name,
                ):
                    raise ValueError("invalid credential environment reference")
                credential = os.environ.get(env_name, "").strip()
                if not credential:
                    raise ValueError("unconfigured principal credential")
                scope = IdentityScope.from_values(**row["scope"])
                authority = authority_for_authenticated_scope(
                    mode, scope=scope,
                    operations=frozenset(OperationClass(op) for op in row["operations"]),
                )
                principals.append(AuthenticatedPrincipal(
                    principal_id=normalize_identifier(row["principal_id"]),
                    authority=authority, identity_scope=scope,
                    credential_digest=hashlib.sha256(credential.encode()).digest(),
                ))
            return cls(tuple(principals))
        except (OSError, TypeError, ValueError, KeyError):
            raise ConfigurationError("invalid principal registry configuration") from None

    def authenticate(self, credential: str) -> AuthenticatedPrincipal | None:
        digest = hashlib.sha256(credential.encode()).digest()
        # Evaluate all entries; never let caller payloads select authority.
        matches = [
            principal for principal in self._principals
            if hmac.compare_digest(digest, principal.credential_digest)
        ]
        return matches[0] if len(matches) == 1 else None
