# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime

import pytest

from cyberbrain.agent_adapter import (
    AgentScope,
    Consequence,
    ContextLedger,
    DreamSignals,
    Observation,
    PredictionIntent,
    RecallKind,
    SessionCloseout,
    TokenBudgetPolicy,
    TurnRecallIntent,
    UniversalAgentAdapter,
)
from tests.agent_adapter.fakes import FakeCyberBrainClient

NOW = datetime(2026, 9, 8, 1, 30, tzinfo=UTC)


@pytest.mark.asyncio
async def test_bootstrap_uses_compact_reads_and_preserves_both_memory_classes() -> None:
    client = FakeCyberBrainClient()
    client.knowledge_rows = [
        {"id": "k1", "recall_text": "k" * 2_000, "recall_text_source": "summary"},
        {"id": "k2", "recall_text": "second knowledge"},
    ]
    client.memory_rows = [
        {"id": "e1", "recall_text": "e" * 2_000, "recall_text_source": "summary"},
        {"id": "e2", "recall_text": "second episode"},
    ]
    client.pending_rows = [{"id": "p1", "expected_outcome": "CI passes"}]
    adapter = UniversalAgentAdapter(
        client,
        budget_policy=TokenBudgetPolicy(bootstrap_tokens=100, chars_per_token=4),
    )
    ledger = ContextLedger(session_id="s1")

    result = await adapter.bootstrap(
        query="CyberBrain adapter",
        scope=AgentScope(session_id="s1", agent="chatgpt", project="CyberBrain"),
        ledger=ledger,
    )

    assert result.context.estimated_tokens <= 100
    assert {item.kind for item in result.context.items} == {
        RecallKind.KNOWLEDGE,
        RecallKind.EPISODE,
    }
    assert result.pending_predictions[0]["id"] == "p1"
    assert ledger.pending_prediction_ids == {"p1"}
    assert client.count("knowledge_search") == 1
    assert client.count("memory_search") == 1
    assert client.count("prediction_pending") == 1
    knowledge_call = next(args for name, args in client.calls if name == "knowledge_search")
    memory_call = next(args for name, args in client.calls if name == "memory_search")
    assert knowledge_call["view"] == "compact"
    assert knowledge_call["project"] == "CyberBrain"
    assert "agent" not in knowledge_call
    assert memory_call["view"] == "compact"
    assert memory_call["agent"] == "chatgpt"
    assert memory_call["project"] == "CyberBrain"
    assert "session_id" not in memory_call
    pending_call = next(args for name, args in client.calls if name == "prediction_pending")
    assert "session_id" not in pending_call


@pytest.mark.asyncio
async def test_ordinary_turn_makes_no_recall_calls() -> None:
    client = FakeCyberBrainClient()
    adapter = UniversalAgentAdapter(client)
    result = await adapter.recall(
        intent=TurnRecallIntent(query="continue"),
        scope=AgentScope(session_id="s1"),
        ledger=ContextLedger(session_id="s1"),
    )
    assert result.items == ()
    assert client.calls == []


@pytest.mark.asyncio
async def test_duplicate_context_is_not_reinjected() -> None:
    client = FakeCyberBrainClient()
    client.knowledge_rows = [{"id": "k1", "recall_text": "known fact"}]
    adapter = UniversalAgentAdapter(client)
    ledger = ContextLedger(session_id="s1")
    intent = TurnRecallIntent(query="fact", need_knowledge=True)
    scope = AgentScope(session_id="s1")

    first = await adapter.recall(intent=intent, scope=scope, ledger=ledger)
    second = await adapter.recall(intent=intent, scope=scope, ledger=ledger)

    assert [item.record_id for item in first.items] == ["k1"]
    assert second.items == ()
    assert client.count("knowledge_search") == 1

    refreshed = await adapter.recall(
        intent=TurnRecallIntent(query="fact", need_knowledge=True, refresh=True),
        scope=scope,
        ledger=ledger,
    )
    assert refreshed.items == ()
    assert refreshed.omitted_ids == ("k1",)
    assert client.count("knowledge_search") == 2


@pytest.mark.asyncio
async def test_full_fetch_requires_selected_id_and_is_limited() -> None:
    client = FakeCyberBrainClient()
    client.knowledge_by_id["k1"] = {"id": "k1", "content": "full"}
    adapter = UniversalAgentAdapter(client)
    ledger = ContextLedger(session_id="s1")

    assert (
        await adapter.fetch_full(record_id="k1", kind=RecallKind.KNOWLEDGE, ledger=ledger)
        is None
    )
    assert client.count("knowledge_get") == 0

    ledger.injected_ids.add("k1")
    row = await adapter.fetch_full(record_id="k1", kind=RecallKind.KNOWLEDGE, ledger=ledger)
    assert row == {"id": "k1", "content": "full"}
    assert client.count("knowledge_get") == 1

    assert (
        await adapter.fetch_full(record_id="k1", kind=RecallKind.KNOWLEDGE, ledger=ledger)
        is None
    )
    assert client.count("knowledge_get") == 1


@pytest.mark.asyncio
async def test_timeline_requires_identity_and_uses_client_protocol() -> None:
    client = FakeCyberBrainClient()
    client.timeline_rows = [{"id": "k1", "content": "v2"}]
    adapter = UniversalAgentAdapter(client)
    scope = AgentScope(session_id="s1")

    with pytest.raises(ValueError, match="timeline_identity"):
        await adapter.recall(
            intent=TurnRecallIntent(query="history", need_timeline=True),
            scope=scope,
            ledger=ContextLedger(session_id="s1"),
        )

    result = await adapter.recall(
        intent=TurnRecallIntent(
            query="history",
            need_timeline=True,
            timeline_identity={
                "domain": "technical",
                "topic": "runtime",
                "entity_type": "service",
                "entity_name": "cyberbrain",
            },
        ),
        scope=scope,
        ledger=ContextLedger(session_id="s1"),
    )
    assert [item.record_id for item in result.items] == ["k1"]
    assert client.count("knowledge_timeline") == 1


@pytest.mark.asyncio
async def test_prediction_record_and_resolution_are_deterministic() -> None:
    client = FakeCyberBrainClient()
    adapter = UniversalAgentAdapter(client)
    scope = AgentScope(session_id="s1", agent="agent-a", project="CyberBrain")
    intent = PredictionIntent(
        expected_outcome="CI succeeds",
        confidence=0.8,
        event_time=NOW,
        outcome_known=False,
        observable_later=True,
        resolvable_with_evidence=True,
        consequence=Consequence.MEDIUM,
        action="push change",
        correlation_id="ci-123",
    )

    decision, prediction = await adapter.maybe_record_prediction(intent=intent, scope=scope)
    assert decision.create is True
    assert prediction is not None
    assert client.count("prediction_record") == 1

    pending = [{"id": "p1", "context": {"correlation_id": "ci-123"}}]
    match, outcome = await adapter.resolve_observation(
        pending_predictions=pending,
        observation=Observation(
            observed_outcome="CI succeeded",
            assessment="confirmed",
            event_time=NOW,
            correlation_id="ci-123",
        ),
    )
    assert match.prediction_id == "p1"
    assert outcome is not None
    assert client.count("prediction_resolve") == 1


@pytest.mark.asyncio
async def test_unmatched_observation_does_not_resolve_prediction() -> None:
    client = FakeCyberBrainClient()
    adapter = UniversalAgentAdapter(client)
    match, outcome = await adapter.resolve_observation(
        pending_predictions=[{"id": "p1"}],
        observation=Observation(
            observed_outcome="unknown result",
            assessment="indeterminate",
            event_time=NOW,
            correlation_id="not-present",
        ),
    )
    assert match.prediction_id is None
    assert match.reason_code == "no_deterministic_match"
    assert outcome is None
    assert client.count("prediction_resolve") == 0


@pytest.mark.asyncio
async def test_trivial_prediction_never_calls_client() -> None:
    client = FakeCyberBrainClient()
    adapter = UniversalAgentAdapter(client)
    decision, result = await adapter.maybe_record_prediction(
        intent=PredictionIntent(
            expected_outcome="directory listing returns",
            confidence=0.99,
            event_time=NOW,
            outcome_known=False,
            observable_later=True,
            resolvable_with_evidence=True,
            consequence=Consequence.TRIVIAL,
        ),
        scope=AgentScope(session_id="s1"),
    )
    assert decision.create is False
    assert result is None
    assert client.count("prediction_record") == 0


@pytest.mark.asyncio
async def test_closeout_is_bounded_and_dream_enqueue_is_selective() -> None:
    client = FakeCyberBrainClient()
    adapter = UniversalAgentAdapter(client, closeout_max_chars=180)
    closeout = SessionCloseout(
        goal="Build universal adapter",
        actions=("implemented lifecycle policy", "implemented token governor"),
        decisions=("keep transport neutral",),
        outcomes=("tests pass",),
        unresolved=("runtime wiring remains coordinator-owned",),
        identifiers=("feat/level8-agent-integration",),
    )
    scope = AgentScope(session_id="s1", agent="agent-a", project="CyberBrain")

    stored, enqueued = await adapter.close_session(
        scope=scope,
        closeout=closeout,
        event_time=NOW,
        dream_signals=DreamSignals(),
    )
    assert len(stored["content"]) <= 180
    assert enqueued is False
    assert client.count("dream_enqueue") == 0

    _, enqueued = await adapter.close_session(
        scope=scope,
        closeout=closeout,
        event_time=NOW,
        dream_signals=DreamSignals(reusable_lesson=True),
    )
    assert enqueued is True
    assert client.count("dream_enqueue") == 1
