# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import json
from time import perf_counter

from cyberbrain.agent_adapter import (
    AgentScope,
    ContextLedger,
    TokenBudgetPolicy,
    TurnRecallIntent,
    UniversalAgentAdapter,
)


class BenchmarkClient:
    def __init__(self) -> None:
        self.calls = 0
        self.full_fetches = 0
        self.rows = [
            {"id": "k1", "recall_text": "Canonical fact " * 40},
            {"id": "k2", "recall_text": "Second fact " * 30},
            {"id": "e1", "recall_text": "Relevant episode " * 35},
        ]

    async def knowledge_search(self, **kwargs):
        self.calls += 1
        return self.rows[:2]

    async def memory_search(self, **kwargs):
        self.calls += 1
        return self.rows[2:]

    async def prediction_pending(self, **kwargs):
        self.calls += 1
        return []

    async def knowledge_get(self, *, record_id):
        self.full_fetches += 1
        return {"id": record_id, "content": "full" * 1_000}

    async def memory_get(self, *, record_id):
        self.full_fetches += 1
        return {"id": record_id, "content": "full" * 1_000}

    async def knowledge_timeline(self, **identity):
        self.calls += 1
        return []

    async def memory_store(self, **kwargs):
        return {"id": "e-closeout", **kwargs}

    async def prediction_record(self, **kwargs):
        return {"id": "p", **kwargs}

    async def prediction_resolve(self, **kwargs):
        return {"id": "o", **kwargs}

    async def dream_enqueue(self, **kwargs):
        return {"status": "queued", **kwargs}


async def run() -> dict[str, float | int]:
    client = BenchmarkClient()
    adapter = UniversalAgentAdapter(
        client,
        budget_policy=TokenBudgetPolicy(bootstrap_tokens=800, targeted_recall_tokens=300),
    )
    ledger = ContextLedger(session_id="bench")
    scope = AgentScope(session_id="bench", agent="bench", project="CyberBrain")

    started = perf_counter()
    bootstrap = await adapter.bootstrap(query="CyberBrain adapter", scope=scope, ledger=ledger)
    first = await adapter.recall(
        intent=TurnRecallIntent(query="canonical fact", need_knowledge=True, need_history=True),
        scope=scope,
        ledger=ledger,
    )
    second = await adapter.recall(
        intent=TurnRecallIntent(query="canonical fact", need_knowledge=True, need_history=True),
        scope=scope,
        ledger=ledger,
    )
    elapsed_ms = (perf_counter() - started) * 1_000

    total_items = len(bootstrap.context.items) + len(first.items) + len(second.items)
    repeat_injections = total_items - len(ledger.injected_ids)
    return {
        "recall_calls_per_task": client.calls,
        "context_estimated_tokens": ledger.consumed_tokens,
        "repeat_injection_count": repeat_injections,
        "full_record_fetch_count": client.full_fetches,
        "policy_latency_ms": round(elapsed_ms, 3),
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), sort_keys=True))
