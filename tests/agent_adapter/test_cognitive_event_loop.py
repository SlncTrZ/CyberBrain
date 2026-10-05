# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cyberbrain.agent_adapter.adapter import UniversalAgentAdapter
from cyberbrain.agent_adapter.models import (
    AgentScope,
    Consequence,
    Observation,
    PredictionIntent,
)
from cyberbrain.cognition.calibration import MetacognitionCalibrationService
from cyberbrain.cognition.heartbeat import CognitiveHeartbeat
from cyberbrain.cognition.prediction import (
    PredictionLearningService,
)
from tests.agent_adapter.fakes import FakeCyberBrainClient


@pytest.mark.asyncio
async def test_adapter_prediction_intent_fails_closed_on_trivial_consequence() -> None:
    client = FakeCyberBrainClient()
    adapter = UniversalAgentAdapter(client)
    scope = AgentScope(session_id="s-test", agent="agent-pi", project="CyberBrain")
    intent = PredictionIntent(
        expected_outcome="Small outcome",
        confidence=0.9,
        event_time=datetime.now(UTC),
        outcome_known=False,
        observable_later=True,
        resolvable_with_evidence=True,
        consequence=Consequence.TRIVIAL,
        action="read_file",
    )

    decision, record = await adapter.record_prediction(intent=intent, scope=scope)

    assert not decision.create
    assert decision.reason_code == "insufficient_consequence"
    assert record is None
    assert client.count("prediction_record") == 0


@pytest.mark.asyncio
async def test_adapter_records_meaningful_prediction_before_action() -> None:
    client = FakeCyberBrainClient()
    adapter = UniversalAgentAdapter(client)
    scope = AgentScope(session_id="s-test", agent="agent-pi", project="CyberBrain")
    intent = PredictionIntent(
        expected_outcome="Build should succeed with 0 errors",
        confidence=0.85,
        event_time=datetime.now(UTC),
        outcome_known=False,
        observable_later=True,
        resolvable_with_evidence=True,
        consequence=Consequence.HIGH,
        action="deploy_patch",
        correlation_id="corr-action-123",
    )

    decision, record = await adapter.record_prediction(
        intent=intent,
        scope=scope,
        strategy_tags=["deployment", "ci"],
    )

    assert decision.create
    assert decision.reason_code == "meaningful_uncertain_outcome"
    assert record is not None
    assert client.count("prediction_record") == 1
    call = client.calls[-1][1]
    assert call["correlation_id"] == "corr-action-123"
    assert call["expected_outcome"] == "Build should succeed with 0 errors"
    assert call["strategy_tags"] == ["deployment", "ci"]


@pytest.mark.asyncio
async def test_adapter_resolves_outcome_matching_correlation_id() -> None:
    client = FakeCyberBrainClient()
    client.pending_rows = [
        {
            "id": "pred-456",
            "prediction_id": "pred-456",
            "expected_outcome": "Build should succeed",
            "correlation_id": "corr-build-99",
            "context": {"correlation_id": "corr-build-99"},
        }
    ]
    adapter = UniversalAgentAdapter(client)
    scope = AgentScope(session_id="s-test", agent="agent-pi", project="CyberBrain")
    observation = Observation(
        observed_outcome="Build completed with 0 errors",
        assessment="confirmed",
        event_time=datetime.now(UTC),
        correlation_id="corr-build-99",
    )

    match, record = await adapter.resolve_prediction(
        observation=observation,
        scope=scope,
    )

    assert match.prediction_id == "pred-456"
    assert match.reason_code == "correlation_id_match"
    assert record is not None
    assert client.count("prediction_resolve") == 1
    call = client.calls[-1][1]
    assert call["prediction_id"] == "pred-456"
    assert call["observed_outcome"] == "Build completed with 0 errors"


def test_cognitive_heartbeat_inspects_work_without_generative_monologue() -> None:
    from cyberbrain.memory.service import MemoryService
    from tests.test_dream_writeback import FakeEmbedding, FakeRepository

    repo = FakeRepository()
    memory = MemoryService(
        repository=repo,
        embedding=FakeEmbedding(),
        collection="cyberbrain_episodic",
    )
    prediction_learning = PredictionLearningService(
        memory=memory,
        repository=repo,
        episodic_collection="cyberbrain_episodic",
    )
    calibration = MetacognitionCalibrationService(prediction_learning=prediction_learning)
    heartbeat = CognitiveHeartbeat(
        prediction_learning=prediction_learning,
        calibration=calibration,
    )

    # Empty run
    summary = heartbeat.run_once()
    assert summary["event"] == "cognitive_heartbeat_summary"
    assert summary["pending_predictions"] == 0
    assert summary["status"] == "idle"

    # Record 1 prediction
    prediction_learning.record_prediction(
        expected_outcome="Tests should pass",
        confidence=0.8,
        session_id="s-1",
        event_time=datetime.now(UTC),
        correlation_id="corr-1",
    )

    summary2 = heartbeat.run_once()
    assert summary2["pending_predictions"] == 1
    assert summary2["status"] == "ready"
    assert summary2["eligible_cognitive_jobs"] == 1
    assert summary2["duplicate_correlations"] == 0


def test_prediction_idempotency_with_correlation_id() -> None:
    from cyberbrain.memory.service import MemoryService
    from tests.test_dream_writeback import FakeEmbedding, FakeRepository

    repo = FakeRepository()
    memory = MemoryService(
        repository=repo,
        embedding=FakeEmbedding(),
        collection="cyberbrain_episodic",
    )
    service = PredictionLearningService(
        memory=memory,
        repository=repo,
        episodic_collection="cyberbrain_episodic",
    )

    first = service.record_prediction(
        expected_outcome="Task completes",
        confidence=0.9,
        session_id="s-idem",
        event_time=datetime.now(UTC),
        correlation_id="corr-idem-1",
    )
    second = service.record_prediction(
        expected_outcome="Task completes duplicate",
        confidence=0.9,
        session_id="s-idem",
        event_time=datetime.now(UTC),
        correlation_id="corr-idem-1",
    )

    assert first.id == second.id
    assert len(repo.points) == 1
