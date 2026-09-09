# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from cyberbrain.schemas.models import IdentityTrust, KnowledgeRecordClass
from cyberbrain.self_model import (
    SelfModelEvidenceDiversity,
    SelfModelEvidenceSample,
    SelfModelHypothesisEngine,
    SelfModelPersistence,
    SelfModelReadinessEvaluator,
    SelfModelReadinessInput,
    SelfModelReviewStatus,
    SelfModelWorkingMemoryAdapter,
)
from cyberbrain.working_memory import TaskRelevance, WorkingMemoryIdentity

NOW = datetime(2026, 9, 8, 13, 0, tzinfo=UTC)


def sample(
    *,
    topic: str,
    session: str,
    assessment: str,
    strategy: str | None = None,
) -> SelfModelEvidenceSample:
    prediction_id = str(uuid4())
    outcome_id = str(uuid4())
    return SelfModelEvidenceSample(
        prediction_id=prediction_id,
        outcome_id=outcome_id,
        agent_id="agent-a",
        session_id=session,
        project="CyberBrain",
        topic=topic,
        assessment=assessment,
        prediction_confidence=0.8,
        prediction_error=0.8 if assessment == "contradicted" else 0.0,
        identity_trust=IdentityTrust.AUTHENTICATED,
        strategy_tags=((strategy,) if strategy else ()),
    )


def ready(samples: tuple[SelfModelEvidenceSample, ...]):  # noqa: ANN201
    evidence_ids = tuple(evidence_id for item in samples for evidence_id in item.evidence_ids)
    return SelfModelReadinessEvaluator().evaluate(
        SelfModelReadinessInput(
            agent_id="agent-a",
            resolved_outcomes=len(samples),
            trusted_resolved_outcomes=len(samples),
            diversity=SelfModelEvidenceDiversity(
                distinct_sessions=len({item.session_id for item in samples}),
                distinct_projects=1,
                distinct_topics=len({item.topic for item in samples}),
            ),
            evidence_ids=evidence_ids,
        )
    )


def fixture_samples() -> tuple[SelfModelEvidenceSample, ...]:
    items: list[SelfModelEvidenceSample] = []
    for index in range(8):
        items.append(
            sample(
                topic="deploy",
                session=f"s{index % 4}",
                assessment="confirmed",
                strategy="check-first",
            )
        )
    for index in range(6):
        items.append(
            sample(
                topic="tests",
                session=f"s{index % 3}",
                assessment="contradicted" if index < 4 else "partially_confirmed",
                strategy="skip-validation",
            )
        )
    for index in range(6):
        items.append(
            sample(
                topic="research",
                session=f"s{index % 3}",
                assessment="confirmed" if index < 4 else "contradicted",
            )
        )
    return tuple(items)


def test_engine_generates_topic_and_strategy_hypotheses_only_after_readiness() -> None:
    samples = fixture_samples()
    readiness = ready(samples)
    assert readiness.ready is True

    hypotheses = SelfModelHypothesisEngine().generate(
        readiness=readiness,
        samples=samples,
        generated_at=NOW,
    )

    by_kind = {hypothesis.kind.value for hypothesis in hypotheses}
    assert "capability" in by_kind
    assert "limitation" in by_kind
    assert "uncertain_capability" in by_kind
    assert "workflow_tendency" in by_kind
    assert "strategy_constraint" in by_kind
    assert all(
        hypothesis.review_status is SelfModelReviewStatus.PENDING for hypothesis in hypotheses
    )
    assert all(hypothesis.support_evidence_ids for hypothesis in hypotheses)


def test_engine_refuses_unready_or_untrusted_sample_set() -> None:
    samples = fixture_samples()[:4]
    readiness = ready(samples)
    assert readiness.ready is False
    assert (
        SelfModelHypothesisEngine().generate(
            readiness=readiness,
            samples=samples,
            generated_at=NOW,
        )
        == ()
    )


class FakeEvolution:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def store(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(kwargs)
        return kwargs


class FakeRepository:
    def scroll(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        return []


def test_only_reviewed_hypothesis_can_persist_or_enter_working_memory() -> None:
    samples = fixture_samples()
    hypothesis = SelfModelHypothesisEngine().generate(
        readiness=ready(samples),
        samples=samples,
        generated_at=NOW,
    )[0]
    evolution = FakeEvolution()
    persistence = SelfModelPersistence(
        evolution=evolution,  # type: ignore[arg-type]
        repository=FakeRepository(),  # type: ignore[arg-type]
        collection="knowledge",
    )

    with pytest.raises(ValueError, match="accepted"):
        persistence.persist(hypothesis)
    with pytest.raises(ValueError, match="accepted"):
        SelfModelWorkingMemoryAdapter.candidate(
            hypothesis,
            identity=WorkingMemoryIdentity("scope", "session", "task"),
            task_relevance=TaskRelevance(0.8),
        )

    accepted = hypothesis.reviewed(
        status=SelfModelReviewStatus.ACCEPTED,
        reviewed_at=NOW,
    )
    result = persistence.persist(accepted)
    assert result["record_class"] is KnowledgeRecordClass.SELF_MODEL_HYPOTHESIS
    assert result["ordinary_recall"] is False
    assert result["agent"] == "agent-a"
    assert all(isinstance(value, UUID) for value in result["evidence_ids"])

    candidate = SelfModelWorkingMemoryAdapter.candidate(
        accepted,
        identity=WorkingMemoryIdentity("scope", "session", "task"),
        task_relevance=TaskRelevance(0.8),
    )
    assert candidate.kind.value == "hypothesis"
    assert candidate.candidate_id.startswith("self-model:")


def test_strategy_hypothesis_requires_multi_session_support() -> None:
    samples = list(fixture_samples())
    single_session_strategy = tuple(
        sample(
            topic=f"other-{index % 3}",
            session="one-session",
            assessment="confirmed",
            strategy="single-session-only",
        )
        for index in range(5)
    )
    combined = tuple(samples) + single_session_strategy
    hypotheses = SelfModelHypothesisEngine().generate(
        readiness=ready(combined),
        samples=combined,
        generated_at=NOW,
    )
    assert not any("single-session-only" in item.claim for item in hypotheses)
