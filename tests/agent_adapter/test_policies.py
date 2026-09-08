# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime

import pytest

from cyberbrain.agent_adapter import (
    CloseoutPolicy,
    Consequence,
    LifecyclePolicy,
    Observation,
    OutcomeMatchPolicy,
    PredictionIntent,
    PredictionPolicy,
    SessionCloseout,
    TurnRecallIntent,
)

NOW = datetime(2026, 9, 8, 1, 0, tzinfo=UTC)


def test_ordinary_turn_requires_zero_recall() -> None:
    assert LifecyclePolicy().recall_operations(TurnRecallIntent(query="continue")) == ()


def test_recall_policy_selects_only_requested_paths() -> None:
    intent = TurnRecallIntent(query="why", need_knowledge=True, need_history=True)
    assert LifecyclePolicy().recall_operations(intent) == (
        "knowledge_search",
        "memory_search",
    )


def test_meaningful_prediction_is_allowed() -> None:
    decision = PredictionPolicy().decide(
        PredictionIntent(
            expected_outcome="CI passes after the adapter change",
            confidence=0.8,
            event_time=NOW,
            outcome_known=False,
            observable_later=True,
            resolvable_with_evidence=True,
            consequence=Consequence.MEDIUM,
        )
    )
    assert decision.create is True
    assert decision.reason_code == "meaningful_uncertain_outcome"


def test_trivial_prediction_is_denied() -> None:
    decision = PredictionPolicy().decide(
        PredictionIntent(
            expected_outcome="ls lists files",
            confidence=0.99,
            event_time=NOW,
            outcome_known=False,
            observable_later=True,
            resolvable_with_evidence=True,
            consequence=Consequence.TRIVIAL,
        )
    )
    assert decision.create is False
    assert decision.reason_code == "insufficient_consequence"


def test_outcome_matches_by_explicit_prediction_id() -> None:
    match = OutcomeMatchPolicy().match(
        [{"id": "p1"}],
        Observation(
            observed_outcome="passed",
            assessment="confirmed",
            event_time=NOW,
            prediction_id="p1",
        ),
    )
    assert match.prediction_id == "p1"
    assert match.reason_code == "prediction_id_match"


def test_outcome_matches_unique_correlation_id_and_rejects_ambiguity() -> None:
    policy = OutcomeMatchPolicy()
    observation = Observation(
        observed_outcome="passed",
        assessment="confirmed",
        event_time=NOW,
        correlation_id="ci-123",
    )
    match = policy.match([{"id": "p1", "context": {"correlation_id": "ci-123"}}], observation)
    assert match.prediction_id == "p1"

    ambiguous = policy.match(
        [
            {"id": "p1", "context": {"correlation_id": "ci-123"}},
            {"id": "p2", "extensions": {"correlation_id": "ci-123"}},
        ],
        observation,
    )
    assert ambiguous.prediction_id is None
    assert ambiguous.reason_code == "ambiguous_correlation_id"


def test_closeout_is_structured_and_bounded() -> None:
    policy = CloseoutPolicy(max_chars=120)
    content = policy.render(
        SessionCloseout(
            goal="Build adapter",
            actions=("implemented policy", "added tests"),
            decisions=("compact first",),
            outcomes=("tests passed",),
            unresolved=("runtime integration deferred",),
            identifiers=("commit abc",),
        )
    )
    assert content.startswith("Goal: Build adapter")
    assert len(content) <= 120


def test_empty_closeout_is_rejected() -> None:
    policy = CloseoutPolicy()
    with pytest.raises(ValueError, match="at least one"):
        policy.render(SessionCloseout(goal=""))
