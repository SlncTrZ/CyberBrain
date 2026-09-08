# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class GateFamily(StrEnum):
    AUTH_ISOLATION = "auth_isolation"
    BACKUP_RESTORE = "backup_restore"
    UPGRADE_MIGRATION = "upgrade_migration"
    RESOURCE_LIMITS = "resource_limits"
    OBSERVABILITY = "observability"
    CLEAN_INSTALL = "clean_install"
    ROLLBACK = "rollback"
    LOAD_ADVERSARIAL = "load_adversarial"
    CONTRACT_COMPATIBILITY = "contract_compatibility"


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    name: str
    family: GateFamily
    passed: bool
    evidence: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("readiness check name must not be empty")
        object.__setattr__(self, "family", GateFamily(self.family))
        object.__setattr__(self, "evidence", self.evidence.strip())


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    ready: bool
    missing_families: tuple[GateFamily, ...]
    failed_checks: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    passed_checks: int
    total_checks: int


class ReadinessEvaluator:
    def __init__(self, required_families: frozenset[GateFamily]) -> None:
        required = frozenset(GateFamily(value) for value in required_families)
        if not required:
            raise ValueError("at least one readiness family must be required")
        self._required = required

    def evaluate(
        self, checks: tuple[ReadinessCheck, ...] | list[ReadinessCheck]
    ) -> ReadinessReport:
        by_family: dict[GateFamily, list[ReadinessCheck]] = {}
        for check in checks:
            by_family.setdefault(check.family, []).append(check)

        missing = tuple(sorted(self._required - set(by_family), key=lambda item: item.value))
        required_checks = [check for check in checks if check.family in self._required]
        failed = tuple(check.name for check in required_checks if not check.passed)
        missing_evidence = tuple(
            check.name for check in required_checks if check.passed and not check.evidence
        )
        return ReadinessReport(
            ready=not missing and not failed and not missing_evidence,
            missing_families=missing,
            failed_checks=failed,
            missing_evidence=missing_evidence,
            passed_checks=sum(
                1 for check in required_checks if check.passed and bool(check.evidence)
            ),
            total_checks=len(required_checks),
        )

    @classmethod
    def agent_ready(cls) -> ReadinessEvaluator:
        return cls(
            frozenset(
                {
                    GateFamily.AUTH_ISOLATION,
                    GateFamily.BACKUP_RESTORE,
                    GateFamily.RESOURCE_LIMITS,
                    GateFamily.OBSERVABILITY,
                    GateFamily.CLEAN_INSTALL,
                    GateFamily.ROLLBACK,
                    GateFamily.CONTRACT_COMPATIBILITY,
                }
            )
        )

    @classmethod
    def multi_user_beta(cls) -> ReadinessEvaluator:
        return cls(frozenset(GateFamily))
