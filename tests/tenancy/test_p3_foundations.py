# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import pytest

from cyberbrain.tenancy import (
    DeploymentMode,
    GateFamily,
    IdentityDimension,
    IdentityScope,
    OperationClass,
    QuotaDecisionInput,
    QuotaLimit,
    QuotaPolicy,
    QuotaResource,
    QuotaScopeKey,
    ReadinessCheck,
    ReadinessEvaluator,
    TenancyOperation,
    TrustedIdentityEvidence,
    authority_from_trusted_identity,
    derive_quota_scope_key,
    evaluate_quota,
    plan_enforcement,
)


def trusted(
    mode: DeploymentMode,
    *,
    scope: IdentityScope,
    operations: frozenset[OperationClass],
):
    evidence = TrustedIdentityEvidence.from_authentication_boundary(
        scope=scope,
        authentication_source="unit-test-auth-boundary",
    )
    return authority_from_trusted_identity(mode, identity=evidence, operations=operations)


def test_plain_mapping_never_becomes_trusted_identity() -> None:
    with pytest.raises(TypeError, match="trusted authenticated identity evidence"):
        authority_from_trusted_identity(  # type: ignore[arg-type]
            DeploymentMode.MULTI_USER,
            identity={"tenant": "tenant-a", "user": "user-a"},
            operations=frozenset({OperationClass.READ}),
        )


def test_plain_string_never_becomes_trusted_identity() -> None:
    with pytest.raises(TypeError, match="trusted authenticated identity evidence"):
        authority_from_trusted_identity(  # type: ignore[arg-type]
            DeploymentMode.AGENT_READY,
            identity="agent-a",
            operations=frozenset({OperationClass.READ}),
        )


def test_trusted_identity_cannot_be_directly_constructed_from_payload_values() -> None:
    with pytest.raises(TypeError, match="from_authentication_boundary"):
        TrustedIdentityEvidence(  # type: ignore[call-arg]
            scope=IdentityScope.from_values(agent="agent-a"),
            authentication_source="payload",
        )


def test_trusted_identity_factory_requires_typed_scope_and_source() -> None:
    with pytest.raises(TypeError, match="IdentityScope"):
        TrustedIdentityEvidence.from_authentication_boundary(  # type: ignore[arg-type]
            scope={"agent": "agent-a"},
            authentication_source="gateway",
        )
    with pytest.raises(ValueError, match="authentication_source"):
        TrustedIdentityEvidence.from_authentication_boundary(
            scope=IdentityScope(),
            authentication_source="   ",
        )


def test_missing_mandatory_identity_fails_closed() -> None:
    evidence = TrustedIdentityEvidence.from_authentication_boundary(
        scope=IdentityScope.from_values(tenant="tenant-a"),
        authentication_source="gateway",
    )
    with pytest.raises(ValueError, match="exactly one user"):
        authority_from_trusted_identity(
            DeploymentMode.MULTI_USER,
            identity=evidence,
            operations=frozenset({OperationClass.READ}),
        )


def test_ambiguous_mandatory_identity_fails_closed() -> None:
    evidence = TrustedIdentityEvidence.from_authentication_boundary(
        scope=IdentityScope.from_values(agent=("agent-a", "agent-b")),
        authentication_source="gateway",
    )
    with pytest.raises(ValueError, match="exactly one agent"):
        authority_from_trusted_identity(
            DeploymentMode.AGENT_READY,
            identity=evidence,
            operations=frozenset({OperationClass.READ}),
        )


def test_wildcard_like_identity_is_rejected_before_trust_conversion() -> None:
    with pytest.raises(ValueError, match="wildcard-like"):
        TrustedIdentityEvidence.from_authentication_boundary(
            scope=IdentityScope.from_values(agent="agent-*"),
            authentication_source="gateway",
        )


@pytest.mark.parametrize(
    ("requested", "reason"),
    [
        (IdentityScope.from_values(tenant="tenant-b"), "SCOPE_WIDENING_TENANT"),
        (IdentityScope.from_values(user="user-b"), "SCOPE_WIDENING_USER"),
    ],
)
def test_multi_user_cross_identity_substitution_denied(
    requested: IdentityScope,
    reason: str,
) -> None:
    authority = trusted(
        DeploymentMode.MULTI_USER,
        scope=IdentityScope.from_values(tenant="tenant-a", user="user-a", project="alpha"),
        operations=frozenset({OperationClass.READ}),
    )
    plan = plan_enforcement(
        authority,
        operation=TenancyOperation.KNOWLEDGE_SEARCH,
        requested_scope=requested,
    )
    assert plan.allow is False
    assert plan.reason_code == reason
    assert plan.storage_filter is None
    assert plan.effective_scope is None


def test_agent_substitution_denied_where_scoped() -> None:
    authority = trusted(
        DeploymentMode.AGENT_READY,
        scope=IdentityScope.from_values(agent="agent-a", project="alpha"),
        operations=frozenset({OperationClass.READ}),
    )
    plan = plan_enforcement(
        authority,
        operation=TenancyOperation.MEMORY_GET,
        requested_scope=IdentityScope.from_values(agent="agent-b"),
    )
    assert plan.allow is False
    assert plan.reason_code == "SCOPE_WIDENING_AGENT"


def test_scope_widening_project_denied() -> None:
    authority = trusted(
        DeploymentMode.AGENT_READY,
        scope=IdentityScope.from_values(agent="agent-a", project="alpha"),
        operations=frozenset({OperationClass.READ}),
    )
    plan = plan_enforcement(
        authority,
        operation=TenancyOperation.KNOWLEDGE_GET,
        requested_scope=IdentityScope.from_values(project=("alpha", "beta")),
    )
    assert plan.allow is False
    assert plan.reason_code == "SCOPE_WIDENING_PROJECT"


def test_absent_requested_scope_inherits_only_granted_values() -> None:
    authority = trusted(
        DeploymentMode.AGENT_READY,
        scope=IdentityScope.from_values(agent="agent-a", project=("alpha", "beta")),
        operations=frozenset({OperationClass.READ}),
    )
    plan = plan_enforcement(
        authority,
        operation=TenancyOperation.KNOWLEDGE_SEARCH,
    )
    assert plan.allow is True
    assert plan.effective_scope is not None
    assert plan.effective_scope.project == frozenset({"alpha", "beta"})
    assert plan.storage_filter is not None
    assert [
        (item.field, item.operator, item.values) for item in plan.storage_filter.conditions
    ] == [
        ("agent", "eq", ("agent-a",)),
        ("project", "in", ("alpha", "beta")),
    ]


def test_read_multi_value_scope_allowed_only_when_grant_allows_it() -> None:
    authority = trusted(
        DeploymentMode.AGENT_READY,
        scope=IdentityScope.from_values(agent="agent-a", project=("alpha", "beta")),
        operations=frozenset({OperationClass.READ}),
    )
    allowed = plan_enforcement(
        authority,
        operation=TenancyOperation.MEMORY_SEARCH,
        requested_scope=IdentityScope.from_values(project=("alpha", "beta")),
    )
    denied = plan_enforcement(
        authority,
        operation=TenancyOperation.MEMORY_SEARCH,
        requested_scope=IdentityScope.from_values(project=("alpha", "gamma")),
    )
    assert allowed.allow is True
    assert allowed.storage_filter is not None
    assert allowed.storage_filter.conditions[-1].operator == "in"
    assert denied.allow is False
    assert denied.reason_code == "SCOPE_WIDENING_PROJECT"


@pytest.mark.parametrize(
    "operation",
    [
        TenancyOperation.KNOWLEDGE_SEARCH,
        TenancyOperation.MEMORY_SEARCH,
        TenancyOperation.KNOWLEDGE_GET,
        TenancyOperation.MEMORY_GET,
        TenancyOperation.KNOWLEDGE_TIMELINE,
    ],
)
def test_read_operation_families_produce_storage_filter(operation: TenancyOperation) -> None:
    authority = trusted(
        DeploymentMode.MULTI_USER,
        scope=IdentityScope.from_values(tenant="tenant-a", user="user-a"),
        operations=frozenset({OperationClass.READ}),
    )
    plan = plan_enforcement(authority, operation=operation)
    assert plan.allow is True
    assert plan.operation_class is OperationClass.READ
    assert plan.storage_filter is not None
    assert plan.storage_filter.fields() >= {"tenant", "user"}
    assert plan.write_attribution is None


def test_background_evidence_read_requires_background_grant_and_filter() -> None:
    authority = trusted(
        DeploymentMode.MULTI_USER,
        scope=IdentityScope.from_values(tenant="tenant-a", user="user-a"),
        operations=frozenset({OperationClass.BACKGROUND_REASONING}),
    )
    plan = plan_enforcement(authority, operation=TenancyOperation.BACKGROUND_EVIDENCE_READ)
    assert plan.allow is True
    assert plan.operation_class is OperationClass.BACKGROUND_REASONING
    assert plan.storage_filter is not None
    assert plan.storage_filter.fields() >= {"tenant", "user"}


def test_operation_not_in_grant_denied_before_filter_or_attribution() -> None:
    authority = trusted(
        DeploymentMode.AGENT_READY,
        scope=IdentityScope.from_values(agent="agent-a"),
        operations=frozenset({OperationClass.READ}),
    )
    plan = plan_enforcement(authority, operation=TenancyOperation.KNOWLEDGE_WRITE)
    assert plan.allow is False
    assert plan.reason_code == "OPERATION_NOT_ALLOWED"
    assert plan.storage_filter is None
    assert plan.write_attribution is None


def test_required_storage_filter_dimensions_cannot_disappear() -> None:
    authority = trusted(
        DeploymentMode.MULTI_USER,
        scope=IdentityScope.from_values(tenant="tenant-a", user="user-a", project="alpha"),
        operations=frozenset({OperationClass.READ}),
    )
    plan = plan_enforcement(authority, operation=TenancyOperation.KNOWLEDGE_TIMELINE)
    assert plan.allow is True
    assert plan.required_dimensions == frozenset(
        {IdentityDimension.TENANT, IdentityDimension.USER}
    )
    assert plan.storage_filter is not None
    assert {"tenant", "user"}.issubset(plan.storage_filter.fields())


@pytest.mark.parametrize(
    "operation",
    [TenancyOperation.KNOWLEDGE_WRITE, TenancyOperation.MEMORY_WRITE],
)
def test_write_multi_value_attribution_denied(operation: TenancyOperation) -> None:
    authority = trusted(
        DeploymentMode.AGENT_READY,
        scope=IdentityScope.from_values(agent="agent-a", project=("alpha", "beta")),
        operations=frozenset({OperationClass.WRITE}),
    )
    plan = plan_enforcement(authority, operation=operation)
    assert plan.allow is False
    assert plan.reason_code == "WRITE_ATTRIBUTION_NOT_SINGLETON"
    assert plan.write_attribution is None


def test_multi_user_write_has_concrete_singleton_tenant_and_user_attribution() -> None:
    authority = trusted(
        DeploymentMode.MULTI_USER,
        scope=IdentityScope.from_values(tenant="tenant-a", user="user-a", project="alpha"),
        operations=frozenset({OperationClass.WRITE}),
    )
    plan = plan_enforcement(authority, operation=TenancyOperation.KNOWLEDGE_WRITE)
    assert plan.allow is True
    assert plan.write_attribution is not None
    assert plan.write_attribution.as_dict() == {
        "tenant": "tenant-a",
        "user": "user-a",
        "project": "alpha",
    }


def test_agent_ready_write_has_singleton_agent_attribution() -> None:
    authority = trusted(
        DeploymentMode.AGENT_READY,
        scope=IdentityScope.from_values(agent="agent-a", project="alpha"),
        operations=frozenset({OperationClass.WRITE}),
    )
    plan = plan_enforcement(authority, operation=TenancyOperation.MEMORY_WRITE)
    assert plan.allow is True
    assert plan.write_attribution is not None
    assert plan.write_attribution.as_dict()["agent"] == "agent-a"


def test_write_narrowing_cannot_substitute_cross_tenant() -> None:
    authority = trusted(
        DeploymentMode.MULTI_USER,
        scope=IdentityScope.from_values(tenant="tenant-a", user="user-a", project="alpha"),
        operations=frozenset({OperationClass.WRITE}),
    )
    plan = plan_enforcement(
        authority,
        operation=TenancyOperation.MEMORY_WRITE,
        requested_scope=IdentityScope.from_values(tenant="tenant-b", project="alpha"),
    )
    assert plan.allow is False
    assert plan.reason_code == "SCOPE_WIDENING_TENANT"


def test_quota_scope_key_requires_concrete_requested_dimensions() -> None:
    scope = IdentityScope.from_values(tenant="tenant-a", user="user-a")
    key = derive_quota_scope_key(
        scope,
        dimensions=frozenset({IdentityDimension.TENANT, IdentityDimension.USER}),
    )
    assert key.values == (("tenant", "tenant-a"), ("user", "user-a"))

    with pytest.raises(ValueError, match="exactly one user"):
        derive_quota_scope_key(
            IdentityScope.from_values(tenant="tenant-a"),
            dimensions=frozenset({IdentityDimension.TENANT, IdentityDimension.USER}),
        )
    with pytest.raises(ValueError, match="exactly one project"):
        derive_quota_scope_key(
            IdentityScope.from_values(project=("alpha", "beta")),
            dimensions=frozenset({IdentityDimension.PROJECT}),
        )
    with pytest.raises(ValueError, match="must not be empty"):
        derive_quota_scope_key(scope, dimensions=frozenset())


def test_quota_scope_key_direct_construction_is_normalized_and_validated() -> None:
    key = QuotaScopeKey((("user", " user-a "), ("tenant", "tenant-a")))
    assert key.values == (("tenant", "tenant-a"), ("user", "user-a"))

    with pytest.raises(ValueError, match="duplicate quota key dimension"):
        QuotaScopeKey((("tenant", "tenant-a"), ("tenant", "tenant-b")))
    with pytest.raises(ValueError, match="wildcard-like"):
        QuotaScopeKey((("tenant", "tenant-*"),))
    with pytest.raises(TypeError, match="must be a tuple"):
        QuotaScopeKey([("tenant", "tenant-a")])  # type: ignore[arg-type]


def test_quota_policy_rejects_invalid_resource_window_combinations() -> None:
    with pytest.raises(ValueError, match="positive"):
        QuotaLimit(QuotaResource.REQUESTS, 0, 60)
    with pytest.raises(ValueError, match="positive"):
        QuotaLimit(QuotaResource.REQUESTS, 1, 0)
    with pytest.raises(ValueError, match="window_seconds required"):
        QuotaLimit(QuotaResource.BACKGROUND_REASONING, 1)
    with pytest.raises(ValueError, match="must not define window_seconds"):
        QuotaLimit(QuotaResource.RECALL_LIMIT, 10, 60)
    with pytest.raises(TypeError, match="amount must be an integer"):
        QuotaLimit(QuotaResource.RECALL_LIMIT, 1.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="amount must be an integer"):
        QuotaLimit(QuotaResource.RECALL_LIMIT, True)
    with pytest.raises(TypeError, match="window_seconds must be an integer"):
        QuotaLimit(QuotaResource.REQUESTS, 1, 1.5)  # type: ignore[arg-type]


def test_quota_decision_input_rejects_nonsensical_usage() -> None:
    key = derive_quota_scope_key(
        IdentityScope.from_values(user="user-a"),
        dimensions=frozenset({IdentityDimension.USER}),
    )
    with pytest.raises(ValueError, match="must not be negative"):
        QuotaDecisionInput(QuotaResource.REQUESTS, key, used=-1)
    with pytest.raises(ValueError, match="must be positive"):
        QuotaDecisionInput(QuotaResource.REQUESTS, key, used=0, requested=0)
    with pytest.raises(TypeError, match="scope_key"):
        QuotaDecisionInput(QuotaResource.REQUESTS, None, used=0)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="used amount must be an integer"):
        QuotaDecisionInput(QuotaResource.REQUESTS, key, used=1.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="requested amount must be an integer"):
        QuotaDecisionInput(QuotaResource.REQUESTS, key, used=0, requested=True)


def test_quota_evaluation_is_deterministic() -> None:
    key = derive_quota_scope_key(
        IdentityScope.from_values(user="user-a"),
        dimensions=frozenset({IdentityDimension.USER}),
    )
    policy = QuotaPolicy((QuotaLimit(QuotaResource.REQUESTS, 10, 60),))
    allowed = evaluate_quota(
        policy,
        QuotaDecisionInput(QuotaResource.REQUESTS, key, used=7, requested=2),
    )
    denied = evaluate_quota(
        policy,
        QuotaDecisionInput(QuotaResource.REQUESTS, key, used=9, requested=2),
    )
    assert (allowed.allow, allowed.reason_code, allowed.remaining) == (True, "QUOTA_ALLOWED", 1)
    assert (denied.allow, denied.reason_code, denied.remaining) == (
        False,
        "QUOTA_EXCEEDED",
        1,
    )


def test_readiness_pass_without_evidence_is_not_ready() -> None:
    report = ReadinessEvaluator(frozenset({GateFamily.AUTH_ISOLATION})).evaluate(
        [ReadinessCheck("cross-tenant isolation", GateFamily.AUTH_ISOLATION, True)]
    )
    assert report.ready is False
    assert report.missing_evidence == ("cross-tenant isolation",)
    assert report.passed_checks == 0


def test_readiness_required_evidence_family_absent_is_not_ready() -> None:
    evaluator = ReadinessEvaluator(
        frozenset({GateFamily.AUTH_ISOLATION, GateFamily.RESOURCE_LIMITS})
    )
    report = evaluator.evaluate(
        [ReadinessCheck("isolation", GateFamily.AUTH_ISOLATION, True, "pytest:test_isolation")]
    )
    assert report.ready is False
    assert report.missing_families == (GateFamily.RESOURCE_LIMITS,)


def test_readiness_requires_passing_evidence_for_each_required_family() -> None:
    evaluator = ReadinessEvaluator(
        frozenset({GateFamily.AUTH_ISOLATION, GateFamily.RESOURCE_LIMITS})
    )
    report = evaluator.evaluate(
        [
            ReadinessCheck("isolation", GateFamily.AUTH_ISOLATION, True, "pytest:isolation"),
            ReadinessCheck("quota", GateFamily.RESOURCE_LIMITS, True, "pytest:quota"),
        ]
    )
    assert report.ready is True
    assert report.missing_evidence == ()
    assert report.passed_checks == 2
