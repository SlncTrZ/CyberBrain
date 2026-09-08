# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime

import pytest

from cyberbrain.agent_adapter import (
    AgentScope,
    ContextLedger,
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
    assert client.count("knowledge_search") == 1
    assert client.count("memory_search") == 1
    assert client.count("prediction_pending") == 0
    knowledge_call = next(args for name, args in client.calls if name == "knowledge_search")
    memory_call = next(args for name, args in client.calls if name == "memory_search")
    assert knowledge_call["view"] == "compact"
    assert knowledge_call["project"] == "CyberBrain"
    assert "agent" not in knowledge_call
    assert memory_call["view"] == "compact"
    assert memory_call["agent"] == "chatgpt"
    assert memory_call["project"] == "CyberBrain"
    assert "session_id" not in memory_call


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
async def test_closeout_stores_bounded_episode_without_orchestrating_dreaming() -> None:
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

    stored = await adapter.close_session(
        scope=scope,
        closeout=closeout,
        event_time=NOW,
    )

    assert len(stored["content"]) <= 180
    assert client.count("memory_store") == 1
    assert client.count("dream_enqueue") == 0
    assert client.count("prediction_pending") == 0
