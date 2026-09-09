# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime

import pytest

from cyberbrain.self_model import (
    SelfModelEvidenceDiversity,
    SelfModelHypothesis,
    SelfModelHypothesisKind,
    SelfModelReadinessEvaluator,
    SelfModelReadinessInput,
    SelfModelReadinessReason,
    SelfModelReadinessStatus,
    SelfModelReviewStatus,
)
from cyberbrain.tenancy import IdentityScope, TrustedIdentityEvidence

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def trusted(agent: str = "agent-a") -> TrustedIdentityEvidence:
    return TrustedIdentityEvidence.from_authentication_boundary(
        scope=IdentityScope.from_values(agent=agent),
        authentication_source="verified-test-boundary",
    )


def evidence(
    *,
    identity: TrustedIdentityEvidence | None = None,
    resolved: int = 2,
    trusted_resolved: int | None = None,
    sessions: int = 2,
    topics: int = 2,
    incomplete: bool = False,
    require_runtime_identity: bool = False,
) -> SelfModelReadinessInput:
    return SelfModelReadinessInput(
        agent_id="agent-a",
        trusted_identity=identity,
        require_runtime_identity=require_runtime_identity,
        resolved_outcomes=resolved,
        trusted_resolved_outcomes=(resolved if trusted_resolved is None else trusted_resolved),
        diversity=SelfModelEvidenceDiversity(
            distinct_sessions=sessions,
            distinct_projects=1,
            distinct_topics=topics,
        ),
        evidence_ids=("p1", "o1", "p2", "o2"),
        may_be_incomplete=incomplete,
    )


def test_current_two_outcome_baseline_is_insufficient_even_with_trusted_identity() -> None:
    report = SelfModelReadinessEvaluator().evaluate(evidence(identity=trusted()))

    assert report.status is SelfModelReadinessStatus.INSUFFICIENT_EVIDENCE
    assert report.ready is False
    assert SelfModelReadinessReason.OUTCOME_SAMPLE_FLOOR_NOT_MET in report.reasons
    assert SelfModelReadinessReason.SESSION_DIVERSITY_NOT_MET in report.reasons
    assert SelfModelReadinessReason.TOPIC_DIVERSITY_NOT_MET in report.reasons
    assert report.minimum_resolved_outcomes == 20


def test_untrusted_historical_outcomes_fail_even_when_total_sample_is_large() -> None:
    report = SelfModelReadinessEvaluator().evaluate(
        evidence(resolved=30, trusted_resolved=0, sessions=0, topics=0)
    )

    assert report.ready is False
    assert SelfModelReadinessReason.UNTRUSTED_OUTCOME_EVIDENCE in report.reasons
    assert SelfModelReadinessReason.OUTCOME_SAMPLE_FLOOR_NOT_MET in report.reasons


def test_runtime_identity_requirement_fails_closed_when_missing() -> None:
    report = SelfModelReadinessEvaluator().evaluate(
        evidence(
            identity=None,
            resolved=30,
            sessions=5,
            topics=5,
            require_runtime_identity=True,
        )
    )

    assert report.ready is False
    assert report.reasons == (SelfModelReadinessReason.TRUSTED_AGENT_IDENTITY_REQUIRED,)


def test_cross_agent_runtime_identity_fails_closed() -> None:
    report = SelfModelReadinessEvaluator().evaluate(
        evidence(
            identity=trusted("agent-b"),
            resolved=30,
            sessions=5,
            topics=5,
            require_runtime_identity=True,
        )
    )

    assert report.ready is False
    assert report.reasons == (SelfModelReadinessReason.TRUSTED_AGENT_IDENTITY_MISMATCH,)


def test_complete_diverse_trusted_sample_can_only_reach_read_only_ready() -> None:
    report = SelfModelReadinessEvaluator().evaluate(
        evidence(identity=trusted(), resolved=20, sessions=3, topics=3)
    )

    assert report.status is SelfModelReadinessStatus.READY_READ_ONLY
    assert report.ready is True
    assert report.reasons == (SelfModelReadinessReason.READ_ONLY_READY,)
    assert report.trusted_identity_source == "verified-test-boundary"


def test_incomplete_scan_fails_closed() -> None:
    report = SelfModelReadinessEvaluator().evaluate(
        evidence(identity=trusted(), resolved=30, sessions=5, topics=5, incomplete=True)
    )

    assert report.ready is False
    assert report.reasons == (SelfModelReadinessReason.EVIDENCE_SCAN_INCOMPLETE,)


def test_hypothesis_contract_requires_traceable_evidence_and_review_state() -> None:
    hypothesis = SelfModelHypothesis(
        hypothesis_id="hypothesis-a",
        agent_id="agent-a",
        kind=SelfModelHypothesisKind.CAPABILITY,
        claim="Validation succeeds consistently in reviewed tasks.",
        support_evidence_ids=("p1", "o1"),
        counterexample_evidence_ids=("o2",),
        confidence=0.7,
        sample_count=20,
        diversity=SelfModelEvidenceDiversity(3, 1, 3),
        generated_at=NOW,
        reason_codes=("repeated_confirmed_outcomes",),
    )

    assert hypothesis.agent_id == "agent-a"
    assert hypothesis.version == "self-model-v2"
    assert hypothesis.review_status is SelfModelReviewStatus.PENDING
    accepted = hypothesis.reviewed(status=SelfModelReviewStatus.ACCEPTED, reviewed_at=NOW)
    assert accepted.accepted is True
    assert accepted.reviewed_at == NOW

    with pytest.raises(ValueError, match="supporting evidence"):
        SelfModelHypothesis(
            hypothesis_id="bad",
            agent_id="agent-a",
            kind=SelfModelHypothesisKind.CAPABILITY,
            claim="unsupported claim",
            support_evidence_ids=(),
            counterexample_evidence_ids=(),
            confidence=0.5,
            sample_count=1,
            diversity=SelfModelEvidenceDiversity(1, 1, 1),
            generated_at=NOW,
            reason_codes=("unsupported",),
        )
