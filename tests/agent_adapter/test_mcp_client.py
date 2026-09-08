# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from cyberbrain.agent_adapter import (
    AgentScope,
    ContextLedger,
    MCPAgentClient,
    RecallKind,
    UniversalAgentAdapter,
)
from cyberbrain.core.errors import ProviderResponseError


class FakeAsyncInvoker:
    def __init__(self) -> None:
        self.responses: dict[str, Any] = {}
        self.errors: dict[str, Exception] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def invoke_async(self, *, tool: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((tool, arguments))
        if tool in self.errors:
            raise self.errors[tool]
        return self.responses[tool]


def run(coro):  # noqa: ANN001, ANN201
    return asyncio.run(coro)


def test_search_maps_canonical_mcp_arguments() -> None:
    invoker = FakeAsyncInvoker()
    invoker.responses["knowledge_search"] = [{"id": "k1", "recall_text": "compact"}]
    client = MCPAgentClient(invoker)

    rows = run(
        client.knowledge_search(
            query="scope auth",
            limit=3,
            view="compact",
            project="CyberBrain",
        )
    )

    assert rows == [{"id": "k1", "recall_text": "compact"}]
    assert invoker.calls == [
        (
            "knowledge_search",
            {
                "query": "scope auth",
                "limit": 3,
                "view": "compact",
                "project": "CyberBrain",
            },
        )
    ]


def test_exact_get_maps_record_id_and_hides_not_found() -> None:
    invoker = FakeAsyncInvoker()
    invoker.errors["knowledge_get"] = ProviderResponseError(
        "not_found: Knowledge record not found",
        error_type="not_found",
    )
    client = MCPAgentClient(invoker)

    assert run(client.knowledge_get(record_id="11111111-1111-1111-1111-111111111111")) is None
    assert invoker.calls[0] == (
        "knowledge_get",
        {"id": "11111111-1111-1111-1111-111111111111"},
    )


def test_exact_get_propagates_non_not_found_provider_errors() -> None:
    invoker = FakeAsyncInvoker()
    invoker.errors["memory_get"] = ProviderResponseError(
        "configuration_error: authority missing",
        error_type="configuration_error",
    )
    client = MCPAgentClient(invoker)

    with pytest.raises(ProviderResponseError, match="authority missing"):
        run(client.memory_get(record_id="11111111-1111-1111-1111-111111111111"))


def test_prediction_pending_unwraps_current_provider_shape() -> None:
    invoker = FakeAsyncInvoker()
    invoker.responses["prediction_pending"] = {
        "items": [{"prediction_id": "p1", "expected_outcome": "tests pass"}],
        "returned": 1,
        "may_be_incomplete": False,
    }
    client = MCPAgentClient(invoker)

    rows = run(client.prediction_pending(limit=4, project="CyberBrain"))

    assert rows == [{"prediction_id": "p1", "expected_outcome": "tests pass"}]
    assert invoker.calls == [
        ("prediction_pending", {"limit": 4, "project": "CyberBrain"})
    ]


def test_write_methods_serialize_datetimes_and_dream_topics() -> None:
    invoker = FakeAsyncInvoker()
    invoker.responses["memory_store"] = {"id": "e1"}
    invoker.responses["prediction_record"] = {"id": "p1"}
    invoker.responses["dream_enqueue"] = {"status": "pending"}
    client = MCPAgentClient(invoker)
    event_time = datetime(2026, 9, 8, 3, 0, tzinfo=UTC)

    run(
        client.memory_store(
            content="closeout",
            session_id="s1",
            event_time=event_time,
            project="CyberBrain",
        )
    )
    run(
        client.prediction_record(
            expected_outcome="tests pass",
            confidence=0.8,
            session_id="s1",
            event_time=event_time,
        )
    )
    run(client.dream_enqueue(session_id="s1", focal_topics=("auth", "recall")))

    assert invoker.calls[0][1]["event_time"] == "2026-09-08T03:00:00+00:00"
    assert invoker.calls[1][1]["event_time"] == "2026-09-08T03:00:00+00:00"
    assert invoker.calls[2] == (
        "dream_enqueue",
        {"session_id": "s1", "topics": ["auth", "recall"]},
    )


def test_universal_adapter_uses_real_client_contract_for_compact_then_exact_fetch() -> None:
    invoker = FakeAsyncInvoker()
    record_id = "11111111-1111-1111-1111-111111111111"
    invoker.responses.update(
        {
            "knowledge_search": [
                {
                    "id": record_id,
                    "score": 0.9,
                    "recall_text": "compact auth decision",
                    "recall_text_source": "summary",
                }
            ],
            "memory_search": [],
            "prediction_pending": {"items": [], "returned": 0, "may_be_incomplete": False},
            "knowledge_get": {
                "id": record_id,
                "content": "full auth decision",
                "project": "CyberBrain",
            },
        }
    )
    adapter = UniversalAgentAdapter(MCPAgentClient(invoker))
    ledger = ContextLedger(session_id="s1")

    bootstrap = run(
        adapter.bootstrap(
            query="auth",
            scope=AgentScope(session_id="s1", project="CyberBrain"),
            ledger=ledger,
        )
    )
    assert bootstrap.context.items[0].record_id == record_id
    full = run(adapter.fetch_full(record_id=record_id, kind=RecallKind.KNOWLEDGE, ledger=ledger))

    assert full is not None
    assert full["content"] == "full auth decision"
    assert [name for name, _ in invoker.calls] == [
        "knowledge_search",
        "memory_search",
        "prediction_pending",
        "knowledge_get",
    ]
