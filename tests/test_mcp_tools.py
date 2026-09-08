# SPDX-License-Identifier: MPL-2.0

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from cyberbrain.knowledge.evolution import EvolutionOutcome, EvolutionResult
from cyberbrain.mcp.server import call_tool, configure_dream_operations, configure_runtime
from cyberbrain.schemas.models import EpisodeRecord, KnowledgeRecord
from cyberbrain.tenancy import (
    DeploymentMode,
    IdentityScope,
    OperationClass,
    TrustedIdentityEvidence,
    authority_for_authenticated_scope,
    bind_authority,
    bind_trusted_identity,
)


class FakeKnowledgeSearch:
    def get(self, **kwargs):
        return {
            "id": str(kwargs["point_id"]),
            "content": "full knowledge content",
            "summary": "knowledge summary",
            "project": "CyberBrain",
        }

    def search(self, **kwargs):
        return [
            {
                "id": "k1",
                "score": 0.9,
                "content": "full knowledge content",
                "summary": "knowledge summary",
                **kwargs,
            }
        ]

    def timeline(self, **kwargs):
        return [{"id": "k1", "version": 1, **kwargs}]


class FakeKnowledgeEvolution:
    def store(self, **kwargs):
        record = KnowledgeRecord(
            content=kwargs["content"],
            domain=kwargs["domain"],
            topic=kwargs["topic"],
            entity_type=kwargs["entity_type"],
            entity_name=kwargs["entity_name"],
            content_hash="0" * 64,
        )
        return EvolutionResult(EvolutionOutcome.INSERT_NEW, record)


class FakeDreamOperations:
    def enqueue(self, **kwargs):
        return {"status": "pending", **kwargs}

    def status(self, **kwargs):
        return {"status": "processed", **kwargs}

    def pending_reviews(self, **kwargs):
        return [{"dream_run_id": "run-1", "candidate_index": 0, **kwargs}]

    def review(self, **kwargs):
        return kwargs


class FakeMemory:
    def get(self, **kwargs):
        return {
            "id": str(kwargs["point_id"]),
            "content": "memory full content",
            "session_id": "s1",
            "project": "CyberBrain",
        }

    def search(self, **kwargs):
        return [
            {
                "id": "e1",
                "score": 0.8,
                "content": "memory full content " * 100,
                "summary": None,
                **kwargs,
            }
        ]

    def store(self, **kwargs):
        return EpisodeRecord(
            id=uuid4(),
            content=kwargs["content"],
            session_id=kwargs["session_id"],
            event_time=kwargs["event_time"],
            content_hash="1" * 64,
        )


class FakePredictionLearning:
    def __init__(self) -> None:
        self.prediction_calls: list[dict] = []
        self.outcome_calls: list[dict] = []
        self.observe_calls: list[dict] = []
        self.pending_calls: list[dict] = []

    def record_prediction(self, **kwargs):
        self.prediction_calls.append(dict(kwargs))
        prediction_id = uuid4()
        return EpisodeRecord(
            id=prediction_id,
            content=f"Prediction: {kwargs['expected_outcome']}",
            session_id=kwargs["session_id"],
            event_time=kwargs["event_time"],
            content_hash="2" * 64,
            source="cognitive_prediction",
            context={
                "cognition": {
                    "kind": "prediction",
                    "prediction_id": str(prediction_id),
                    "expected_outcome": kwargs["expected_outcome"],
                    "confidence": kwargs["confidence"],
                }
            },
        )

    def record_outcome(
        self,
        *,
        prediction_id,
        observed_outcome,
        assessment,
        event_time,
        required_agent=None,
    ):
        kwargs = {
            "prediction_id": prediction_id,
            "observed_outcome": observed_outcome,
            "assessment": assessment,
            "event_time": event_time,
            "required_agent": required_agent,
        }
        self.outcome_calls.append(dict(kwargs))
        return EpisodeRecord(
            id=uuid4(),
            content=f"Outcome: {observed_outcome}",
            session_id="s-prediction",
            event_time=event_time,
            content_hash="3" * 64,
            source="cognitive_outcome",
            context={
                "cognition": {
                    "kind": "outcome",
                    "prediction_id": str(prediction_id),
                    "observed_outcome": observed_outcome,
                    "assessment": assessment,
                }
            },
        )

    def observe(self, **kwargs):
        from cyberbrain.cognition.prediction import PredictionObservation

        self.observe_calls.append(dict(kwargs))
        return PredictionObservation(
            predictions_total=3,
            outcomes_total=2,
            resolved_predictions=2,
            unresolved_predictions=1,
            duplicate_outcomes=0,
            mean_prediction_confidence=0.7,
            mean_confidence_weighted_error=0.25,
            assessment_counts={
                "confirmed": 1,
                "partially_confirmed": 0,
                "contradicted": 1,
                "indeterminate": 0,
            },
            error_class_counts={
                "none": 1,
                "partial": 0,
                "full": 1,
                "indeterminate": 0,
            },
            may_be_truncated=False,
            sample_limit=int(kwargs.get("limit", 1000)),
            filters={
                key: str(value)
                for key, value in kwargs.items()
                if key != "limit" and value is not None
            },
        )

    def pending(self, **kwargs):
        from cyberbrain.cognition.prediction import (
            PendingPrediction,
            PendingPredictionList,
        )

        self.pending_calls.append(dict(kwargs))
        return PendingPredictionList(
            items=[
                PendingPrediction(
                    prediction_id=uuid4(),
                    event_time=datetime.now(UTC),
                    expected_outcome="Pending outcome.",
                    confidence=0.6,
                    action="validate",
                    session_id="s-prediction",
                    channel="mcp",
                    agent="agent-a",
                    project="CyberBrain",
                    topic="validation",
                )
            ],
            returned=1,
            may_be_incomplete=False,
            scan_limit=int(kwargs.get("scan_limit", 10000)),
            filters={
                key: str(value)
                for key, value in kwargs.items()
                if key not in {"limit", "scan_limit"} and value is not None
            },
        )


PREDICTION_LEARNING = FakePredictionLearning()


@dataclass
class FakeCalibration:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def observe(self, **kwargs):
        from cyberbrain.cognition.calibration import (
            CalibrationAssessment,
            CalibrationReport,
        )

        self.calls.append(dict(kwargs))
        return CalibrationReport(
            usable_samples=25,
            excluded_indeterminate=2,
            minimum_samples=int(kwargs.get("minimum_samples", 20)),
            mean_confidence=0.72,
            mean_empirical_score=0.6,
            calibration_bias=0.12,
            mean_squared_calibration_error=0.08,
            assessment=CalibrationAssessment.OVERCONFIDENT,
            bias_threshold=float(kwargs.get("bias_threshold", 0.1)),
            may_be_incomplete=False,
            filters={
                key: str(value)
                for key, value in kwargs.items()
                if key not in {"limit", "minimum_samples", "bias_threshold"}
                and value is not None
            },
        )


CALIBRATION = FakeCalibration()


@dataclass
class FakeRuntime:
    knowledge_evolution: FakeKnowledgeEvolution
    knowledge_search: FakeKnowledgeSearch
    memory: FakeMemory
    prediction_learning: FakePredictionLearning
    metacognition_calibration: FakeCalibration


def setup_module() -> None:
    configure_runtime(
        FakeRuntime(
            FakeKnowledgeEvolution(),
            FakeKnowledgeSearch(),
            FakeMemory(),
            PREDICTION_LEARNING,
            CALIBRATION,
        )
    )
    configure_dream_operations(FakeDreamOperations())


CALLER_AUTHORITY = authority_for_authenticated_scope(
    DeploymentMode.SINGLE_OWNER,
    scope=IdentityScope(),
    operations=frozenset(OperationClass),
)


def _call(name: str, args: dict) -> dict | list:
    with bind_authority(CALLER_AUTHORITY):
        result = asyncio.run(call_tool(name, args))
    return json.loads(result[0].text)


def _call_trusted(name: str, args: dict, *, agent: str = "agent-a") -> dict | list:
    identity = TrustedIdentityEvidence.from_authentication_boundary(
        scope=IdentityScope.from_values(agent=agent),
        authentication_source="unit-test-auth-boundary",
    )
    with bind_authority(CALLER_AUTHORITY), bind_trusted_identity(identity):
        result = asyncio.run(call_tool(name, args))
    return json.loads(result[0].text)


def test_help_describes_agent_memory_boundary_and_automatic_dream_lifecycle() -> None:
    text = asyncio.run(call_tool("help", {}))[0].text

    assert "Normal external agents are memory consumers/producers" in text
    assert (
        "server-side Dream scheduler later discovers eligible quiet sessions automatically"
        in text
    )
    assert "advanced override/control path" in text
    assert "Do not fabricate a Prediction retrospectively" in text


def test_knowledge_search_handler() -> None:
    result = _call("knowledge_search", {"query": "x", "domain": "ops", "limit": 3})
    assert result[0]["query"] == "x"
    assert result[0]["domain"] == "ops"
    assert result[0]["limit"] == 3
    assert result[0]["recall_text"] == "knowledge summary"
    assert result[0]["recall_text_source"] == "summary"
    assert result[0]["content_chars"] == len("full knowledge content")
    assert result[0]["content_omitted"] is True
    assert "content" not in result[0]
    assert "summary" not in result[0]


def test_knowledge_search_full_view_preserves_canonical_payload() -> None:
    result = _call("knowledge_search", {"query": "x", "view": "full"})
    assert result[0]["content"] == "full knowledge content"
    assert result[0]["summary"] == "knowledge summary"
    assert "recall_text" not in result[0]
    assert "view" not in result[0]


def test_knowledge_get_handler_returns_exact_full_record() -> None:
    point_id = uuid4()
    result = _call("knowledge_get", {"id": str(point_id)})
    assert result["id"] == str(point_id)
    assert result["content"] == "full knowledge content"
    assert result["summary"] == "knowledge summary"


def test_knowledge_store_handler() -> None:
    result = _call(
        "knowledge_store",
        {
            "content": "Use authenticated MCP.",
            "domain": "ops",
            "topic": "mcp",
            "entity_type": "decision",
            "entity_name": "auth",
        },
    )
    assert result["outcome"] == "insert_new"
    assert result["record"]["entity_name"] == "auth"


def test_memory_get_handler_returns_exact_full_record() -> None:
    point_id = uuid4()
    result = _call("memory_get", {"id": str(point_id)})
    assert result["id"] == str(point_id)
    assert result["content"] == "memory full content"
    assert result["session_id"] == "s1"


def test_memory_store_handler_parses_datetime() -> None:
    result = _call(
        "memory_store",
        {
            "content": "session note",
            "session_id": "s1",
            "event_time": datetime.now(UTC).isoformat(),
        },
    )
    assert result["session_id"] == "s1"


def test_memory_search_handler_applies_filters() -> None:
    result = _call("memory_search", {"query": "x", "channel": "chatgpt", "limit": 2})
    assert result[0]["channel"] == "chatgpt"
    assert result[0]["limit"] == 2
    assert result[0]["recall_text_source"] == "content_excerpt"
    assert len(result[0]["recall_text"]) == 1200
    assert result[0]["content_chars"] == len("memory full content " * 100)
    assert result[0]["content_omitted"] is True
    assert "content" not in result[0]
    assert "summary" not in result[0]


def test_memory_search_full_view_preserves_canonical_payload() -> None:
    result = _call("memory_search", {"query": "x", "view": "full"})
    assert result[0]["content"] == "memory full content " * 100
    assert result[0]["summary"] is None
    assert "recall_text" not in result[0]
    assert "view" not in result[0]


def test_prediction_record_handler_parses_datetime_and_confidence() -> None:
    result = _call(
        "prediction_record",
        {
            "expected_outcome": "The validation passes.",
            "confidence": 0.75,
            "session_id": "s-prediction",
            "event_time": datetime.now(UTC).isoformat(),
            "project": "CyberBrain",
        },
    )

    cognition = result["context"]["cognition"]
    assert result["source"] == "cognitive_prediction"
    assert cognition["kind"] == "prediction"
    assert cognition["confidence"] == 0.75
    assert PREDICTION_LEARNING.prediction_calls[-1]["project"] == "CyberBrain"


def test_prediction_record_uses_trusted_agent_and_rejects_payload_substitution() -> None:
    base = {
        "expected_outcome": "Trusted attribution is retained.",
        "confidence": 0.8,
        "session_id": "s-trusted",
        "event_time": datetime.now(UTC).isoformat(),
    }

    _call_trusted("prediction_record", dict(base))
    assert PREDICTION_LEARNING.prediction_calls[-1]["agent"] == "agent-a"

    rejected = _call_trusted("prediction_record", {**base, "agent": "agent-b"})
    assert rejected["error"]["type"] == "configuration_error"
    assert "does not match trusted caller identity" in rejected["error"]["message"]


def test_prediction_reads_are_narrowed_to_trusted_agent() -> None:
    _call_trusted("prediction_observe", {"project": "CyberBrain", "limit": 50})
    assert PREDICTION_LEARNING.observe_calls[-1]["agent"] == "agent-a"

    _call_trusted("prediction_pending", {"project": "CyberBrain", "limit": 10})
    assert PREDICTION_LEARNING.pending_calls[-1]["agent"] == "agent-a"

    _call_trusted("calibration_observe", {"project": "CyberBrain"})
    assert CALIBRATION.calls[-1]["agent"] == "agent-a"

    rejected = _call_trusted("prediction_observe", {"agent": "agent-b"})
    assert rejected["error"]["type"] == "configuration_error"


def test_prediction_resolve_passes_required_trusted_agent() -> None:
    prediction_id = uuid4()
    _call_trusted(
        "prediction_resolve",
        {
            "prediction_id": str(prediction_id),
            "observed_outcome": "done",
            "assessment": "confirmed",
            "event_time": datetime.now(UTC).isoformat(),
        },
    )
    assert PREDICTION_LEARNING.outcome_calls[-1]["required_agent"] == "agent-a"


def test_prediction_observe_handler_returns_read_only_summary() -> None:
    result = _call(
        "prediction_observe",
        {
            "project": "CyberBrain",
            "agent": "agent-a",
            "limit": 50,
        },
    )

    assert result["predictions_total"] == 3
    assert result["resolved_predictions"] == 2
    assert result["unresolved_predictions"] == 1
    assert result["assessment_counts"]["contradicted"] == 1
    assert PREDICTION_LEARNING.observe_calls[-1] == {
        "project": "CyberBrain",
        "agent": "agent-a",
        "limit": 50,
    }


def test_prediction_pending_handler_returns_unresolved_predictions() -> None:
    result = _call(
        "prediction_pending",
        {
            "project": "CyberBrain",
            "agent": "agent-a",
            "limit": 10,
            "scan_limit": 500,
        },
    )

    assert result["returned"] == 1
    assert result["items"][0]["expected_outcome"] == "Pending outcome."
    assert result["items"][0]["confidence"] == 0.6
    assert result["may_be_incomplete"] is False
    assert PREDICTION_LEARNING.pending_calls[-1] == {
        "project": "CyberBrain",
        "agent": "agent-a",
        "limit": 10,
        "scan_limit": 500,
    }


def test_calibration_observe_handler_returns_read_only_report() -> None:
    result = _call(
        "calibration_observe",
        {
            "agent": "agent-a",
            "project": "CyberBrain",
            "minimum_samples": 20,
            "bias_threshold": 0.1,
        },
    )

    assert result["usable_samples"] == 25
    assert result["assessment"] == "overconfident"
    assert result["calibration_bias"] == 0.12
    assert CALIBRATION.calls[-1] == {
        "agent": "agent-a",
        "project": "CyberBrain",
        "minimum_samples": 20,
        "bias_threshold": 0.1,
    }


def test_prediction_resolve_handler_parses_uuid_and_assessment() -> None:
    prediction_id = uuid4()
    result = _call(
        "prediction_resolve",
        {
            "prediction_id": str(prediction_id),
            "observed_outcome": "The validation failed.",
            "assessment": "contradicted",
            "event_time": datetime.now(UTC).isoformat(),
        },
    )

    call = PREDICTION_LEARNING.outcome_calls[-1]
    assert isinstance(call["prediction_id"], UUID)
    assert call["prediction_id"] == prediction_id
    assert call["assessment"] == "contradicted"
    assert result["context"]["cognition"]["kind"] == "outcome"


def test_legacy_knowledge_search_normalizes_wing_to_domain() -> None:
    result = _call("knowledge_search", {"query": "x", "wing": "Operations", "limit": 3})
    assert result[0]["domain"] == "operations"
    assert result[0]["query"] == "x"


def test_ai_memory_read_combines_knowledge_and_memory() -> None:
    result = _call("ai_memory_read", {"query": "remember"})
    assert result["knowledge"][0]["query"] == "remember"
    assert result["memory"][0]["query"] == "remember"


def test_conversation_recall_maps_to_memory_search() -> None:
    result = _call(
        "conversation_recall",
        {"query": "hello", "channel": "telegram", "limit": 4},
    )
    assert result[0]["query"] == "hello"
    assert result[0]["channel"] == "telegram"
    assert result[0]["limit"] == 4


def test_dream_enqueue_handler() -> None:
    result = _call(
        "dream_enqueue",
        {"session_id": "session-1", "topics": ["CyberBrain", "MCP"]},
    )
    assert result["status"] == "pending"
    assert result["session_id"] == "session-1"
    assert result["topics"] == ["CyberBrain", "MCP"]


def test_dream_status_handler() -> None:
    result = _call("dream_status", {"session_id": "session-1"})
    assert result == {"status": "processed", "session_id": "session-1"}


def test_dream_reviews_handler() -> None:
    result = _call("dream_reviews", {"limit": 10})
    assert result == [{"dream_run_id": "run-1", "candidate_index": 0, "limit": 10}]


def test_dream_review_resolve_handler() -> None:
    result = _call(
        "dream_review_resolve",
        {
            "dream_run_id": "run-1",
            "candidate_index": 0,
            "resolution": "approved",
            "reviewer": "human:test",
            "reason": "checked",
        },
    )
    assert result["resolution"] == "approved"
    assert result["reviewer"] == "human:test"


def test_unknown_tool_returns_stable_not_found_error() -> None:
    result = _call("does_not_exist", {})
    assert result == {
        "error": {
            "type": "not_found",
            "message": "Unknown tool: does_not_exist",
            "retryable": False,
        }
    }


def test_invalid_recall_view_returns_validation_error() -> None:
    result = _call("knowledge_search", {"query": "x", "view": "verbose"})
    assert result["error"]["type"] == "validation_error"
    assert result["error"]["retryable"] is False


def test_invalid_tool_arguments_return_validation_error() -> None:
    result = _call(
        "memory_store",
        {
            "content": "session note",
            "session_id": "s1",
            "event_time": "not-a-date",
        },
    )
    assert result["error"]["type"] == "validation_error"
    assert result["error"]["retryable"] is False


def test_tool_handler_does_not_mutate_input_arguments() -> None:
    args = {"query": "x", "domain": "ops", "limit": 3}
    original = dict(args)

    _call("knowledge_search", args)

    assert args == original
