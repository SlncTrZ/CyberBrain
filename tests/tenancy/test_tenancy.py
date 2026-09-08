# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import pytest

from cyberbrain.tenancy import (
    AuthorityGrant,
    DeploymentMode,
    GateFamily,
    IdentityDimension,
    IdentityScope,
    OperationClass,
    QuotaLimit,
    QuotaPolicy,
    QuotaResource,
    ReadinessCheck,
    ReadinessEvaluator,
    ScopeAuthorizationPolicy,
    ScopeRequirements,
    authority_for_authenticated_scope,
    build_storage_filter,
    build_write_attribution,
    deployment_identity_profile,
    normalize_identifier,
)


def grant(*, projects=("alpha", "beta"), operations=(OperationClass.READ, OperationClass.WRITE)):
    return AuthorityGrant(
        scope=IdentityScope.from_values(
            tenant="tenant-a",
            user="user-a",
            agent="agent-a",
            project=projects,
        ),
        operations=frozenset(operations),
    )


def requirements(*dims: IdentityDimension) -> ScopeRequirements:
    return ScopeRequirements(frozenset(dims))


def test_deployment_profiles_define_minimum_authenticated_identity() -> None:
    assert deployment_identity_profile(DeploymentMode.SINGLE_OWNER).minimum_identity_dimensions == (
        frozenset()
    )
    assert deployment_identity_profile(DeploymentMode.AGENT_READY).minimum_identity_dimensions == (
        frozenset({IdentityDimension.AGENT})
    )
    assert deployment_identity_profile(DeploymentMode.MULTI_USER).minimum_identity_dimensions == (
        frozenset({IdentityDimension.TENANT, IdentityDimension.USER})
    )


def test_single_owner_authenticated_scope_maps_to_authority_grant() -> None:
    authority = authority_for_authenticated_scope(
        DeploymentMode.SINGLE_OWNER,
        scope=IdentityScope(),
        operations=frozenset(OperationClass),
    )
    assert authority.deployment_mode is DeploymentMode.SINGLE_OWNER
    assert authority.grant.scope == IdentityScope()
    assert authority.grant.operations == frozenset(OperationClass)


def test_agent_ready_requires_one_authenticated_agent_identity() -> None:
    with pytest.raises(ValueError, match="exactly one agent"):
        authority_for_authenticated_scope(
            DeploymentMode.AGENT_READY,
            scope=IdentityScope(),
            operations=frozenset({OperationClass.READ}),
        )

    authority = authority_for_authenticated_scope(
        DeploymentMode.AGENT_READY,
        scope=IdentityScope.from_values(agent="agent-a"),
        operations=frozenset({OperationClass.READ}),
    )
    assert authority.grant.scope.agent == frozenset({"agent-a"})


def test_multi_user_requires_concrete_tenant_and_user_identity() -> None:
    with pytest.raises(ValueError, match="exactly one user|exactly one tenant"):
        authority_for_authenticated_scope(
            DeploymentMode.MULTI_USER,
            scope=IdentityScope.from_values(tenant="tenant-a"),
            operations=frozenset({OperationClass.READ}),
        )

    authority = authority_for_authenticated_scope(
        DeploymentMode.MULTI_USER,
        scope=IdentityScope.from_values(tenant="tenant-a", user="user-a"),
        operations=frozenset({OperationClass.READ}),
    )
    assert authority.grant.scope.tenant == frozenset({"tenant-a"})
    assert authority.grant.scope.user == frozenset({"user-a"})


def test_identifier_normalization_trims_but_preserves_case() -> None:
    assert normalize_identifier("  CyberBrain  ") == "CyberBrain"


@pytest.mark.parametrize("value", ["", "   ", "*", "all", "ANY", "foo*", "__all__"])
def test_wildcard_like_identifiers_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_identifier(value)


def test_control_character_identifier_rejected() -> None:
    with pytest.raises(ValueError):
        normalize_identifier("tenant\nother")


def test_scope_normalizes_and_deduplicates_values() -> None:
    scope = IdentityScope.from_values(project=[" alpha ", "alpha", "beta"])
    assert scope.project == frozenset({"alpha", "beta"})


def test_valid_project_narrowing() -> None:
    decision = ScopeAuthorizationPolicy.decide(
        grant(),
        requested_scope=IdentityScope.from_values(project="alpha"),
        operation=OperationClass.READ,
        requirements=requirements(IdentityDimension.TENANT, IdentityDimension.PROJECT),
    )
    assert decision.allow is True
    assert decision.effective_scope is not None
    assert decision.effective_scope.project == frozenset({"alpha"})
    assert decision.effective_scope.tenant == frozenset({"tenant-a"})


def test_same_cardinality_project_substitution_attack_denied() -> None:
    decision = ScopeAuthorizationPolicy.decide(
        grant(projects=("alpha", "beta")),
        requested_scope=IdentityScope.from_values(project=("alpha", "gamma")),
        operation=OperationClass.READ,
    )
    assert decision.allow is False
    assert decision.reason_code == "SCOPE_WIDENING_PROJECT"


def test_tenant_substitution_denied() -> None:
    decision = ScopeAuthorizationPolicy.decide(
        grant(),
        requested_scope=IdentityScope.from_values(tenant="tenant-b"),
        operation=OperationClass.READ,
    )
    assert decision.allow is False
    assert decision.reason_code == "SCOPE_WIDENING_TENANT"


def test_user_substitution_denied() -> None:
    decision = ScopeAuthorizationPolicy.decide(
        grant(),
        requested_scope=IdentityScope.from_values(user="user-b"),
        operation=OperationClass.READ,
    )
    assert decision.allow is False
    assert decision.reason_code == "SCOPE_WIDENING_USER"


def test_agent_substitution_denied() -> None:
    decision = ScopeAuthorizationPolicy.decide(
        grant(),
        requested_scope=IdentityScope.from_values(agent="agent-b"),
        operation=OperationClass.READ,
    )
    assert decision.allow is False
    assert decision.reason_code == "SCOPE_WIDENING_AGENT"


def test_request_cannot_introduce_ungranted_session() -> None:
    decision = ScopeAuthorizationPolicy.decide(
        grant(),
        requested_scope=IdentityScope.from_values(session="session-1"),
        operation=OperationClass.READ,
    )
    assert decision.allow is False
    assert decision.reason_code == "SCOPE_WIDENING_SESSION"


def test_missing_required_dimension_fails_closed() -> None:
    shallow = AuthorityGrant(
        IdentityScope.from_values(project="alpha"), frozenset({OperationClass.READ})
    )
    decision = ScopeAuthorizationPolicy.decide(
        shallow,
        requested_scope=IdentityScope(),
        operation=OperationClass.READ,
        requirements=requirements(IdentityDimension.TENANT),
    )
    assert decision.allow is False
    assert decision.reason_code == "REQUIRED_SCOPE_MISSING_TENANT"


def test_operation_class_denied() -> None:
    read_only = grant(operations=(OperationClass.READ,))
    decision = ScopeAuthorizationPolicy.decide(
        read_only, requested_scope=IdentityScope(), operation=OperationClass.ADMIN_REVIEW
    )
    assert decision.allow is False
    assert decision.reason_code == "OPERATION_NOT_ALLOWED"


def test_empty_request_inherits_but_never_expands_grant() -> None:
    decision = ScopeAuthorizationPolicy.decide(
        grant(projects=("alpha", "beta")),
        requested_scope=IdentityScope(),
        operation=OperationClass.READ,
    )
    assert decision.allow is True
    assert decision.effective_scope is not None
    assert decision.effective_scope.project == frozenset({"alpha", "beta"})


def test_storage_filter_is_deterministic_and_complete() -> None:
    scope = IdentityScope.from_values(tenant="tenant-a", user="user-a", project=("beta", "alpha"))
    result = build_storage_filter(
        scope, required_dimensions=frozenset({IdentityDimension.TENANT, IdentityDimension.PROJECT})
    )
    assert [(c.field, c.operator, c.values) for c in result.conditions] == [
        ("tenant", "eq", ("tenant-a",)),
        ("user", "eq", ("user-a",)),
        ("project", "in", ("alpha", "beta")),
    ]
    assert result.fields() == frozenset({"tenant", "user", "project"})


def test_storage_filter_refuses_missing_required_dimension() -> None:
    with pytest.raises(ValueError, match="required scope missing: tenant"):
        build_storage_filter(
            IdentityScope.from_values(project="alpha"),
            required_dimensions=frozenset({IdentityDimension.TENANT}),
        )


def test_write_attribution_requires_concrete_single_value() -> None:
    with pytest.raises(ValueError, match="must resolve one value for project"):
        build_write_attribution(
            IdentityScope.from_values(tenant="tenant-a", project=("alpha", "beta")),
            required_dimensions=frozenset({IdentityDimension.TENANT, IdentityDimension.PROJECT}),
        )


def test_write_attribution_is_stable_for_narrowed_scope() -> None:
    decision = ScopeAuthorizationPolicy.decide(
        grant(),
        requested_scope=IdentityScope.from_values(project="alpha"),
        operation=OperationClass.WRITE,
        requirements=requirements(IdentityDimension.TENANT, IdentityDimension.PROJECT),
    )
    assert decision.allow is True and decision.effective_scope is not None
    attribution = build_write_attribution(
        decision.effective_scope,
        required_dimensions=frozenset({IdentityDimension.TENANT, IdentityDimension.PROJECT}),
    )
    assert attribution.as_dict() == {
        "tenant": "tenant-a",
        "user": "user-a",
        "agent": "agent-a",
        "project": "alpha",
    }


def test_cross_tenant_write_cannot_reach_attribution() -> None:
    decision = ScopeAuthorizationPolicy.decide(
        grant(),
        requested_scope=IdentityScope.from_values(tenant="tenant-b", project="alpha"),
        operation=OperationClass.WRITE,
    )
    assert decision.allow is False
    assert decision.effective_scope is None


def test_quota_policy_validation_and_lookup() -> None:
    policy = QuotaPolicy(
        (
            QuotaLimit(QuotaResource.REQUESTS, 120, 60),
            QuotaLimit(QuotaResource.RECALL_LIMIT, 10),
            QuotaLimit(QuotaResource.DREAM_ENQUEUE, 6, 3600),
        )
    )
    assert policy.limit_for(QuotaResource.REQUESTS).amount == 120
    assert policy.limit_for(QuotaResource.WRITES) is None


def test_time_window_quota_requires_window() -> None:
    with pytest.raises(ValueError, match="window_seconds required"):
        QuotaLimit(QuotaResource.WRITES, 5)


def test_duplicate_quota_resource_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate resources"):
        QuotaPolicy(
            (
                QuotaLimit(QuotaResource.RECALL_LIMIT, 5),
                QuotaLimit(QuotaResource.RECALL_LIMIT, 10),
            )
        )


def test_readiness_missing_family_is_not_ready() -> None:
    evaluator = ReadinessEvaluator(
        frozenset({GateFamily.AUTH_ISOLATION, GateFamily.BACKUP_RESTORE})
    )
    report = evaluator.evaluate(
        [ReadinessCheck("isolation adversarial", GateFamily.AUTH_ISOLATION, True, "tests")]
    )
    assert report.ready is False
    assert report.missing_families == (GateFamily.BACKUP_RESTORE,)


def test_readiness_failed_check_is_not_ready() -> None:
    evaluator = ReadinessEvaluator(frozenset({GateFamily.AUTH_ISOLATION}))
    report = evaluator.evaluate(
        [ReadinessCheck("cross tenant", GateFamily.AUTH_ISOLATION, False, "failed")]
    )
    assert report.ready is False
    assert report.failed_checks == ("cross tenant",)


def test_readiness_all_required_families_pass() -> None:
    required = frozenset({GateFamily.AUTH_ISOLATION, GateFamily.ROLLBACK})
    evaluator = ReadinessEvaluator(required)
    report = evaluator.evaluate(
        [
            ReadinessCheck("isolation", GateFamily.AUTH_ISOLATION, True, "pytest"),
            ReadinessCheck("rollback", GateFamily.ROLLBACK, True, "pytest"),
        ]
    )
    assert report.ready is True
    assert report.passed_checks == 2
    assert report.total_checks == 2


def test_multi_user_beta_requires_every_gate_family() -> None:
    checks = [ReadinessCheck(family.value, family, True, "pytest") for family in GateFamily]
    assert ReadinessEvaluator.multi_user_beta().evaluate(checks).ready is True
    assert ReadinessEvaluator.multi_user_beta().evaluate(checks[:-1]).ready is False
