# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from cyberbrain.agent_adapter.budgeting import TokenBudgetPolicy, TokenGovernor
from cyberbrain.agent_adapter.contracts import CyberBrainClient
from cyberbrain.agent_adapter.models import (
    AgentScope,
    ContextLedger,
    ContextPack,
    RecallCandidate,
    RecallKind,
    SessionCloseout,
    TurnRecallIntent,
)
from cyberbrain.agent_adapter.policies import CloseoutPolicy, LifecyclePolicy


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    context: ContextPack


class UniversalAgentAdapter:
    """Foreground memory/context helper over a transport-neutral CyberBrain client.

    The adapter consumes and produces memory only. Background cognition, including Dream
    scheduling/processing and Knowledge Evolution, remains CyberBrain-owned.
    """

    def __init__(
        self,
        client: CyberBrainClient,
        *,
        budget_policy: TokenBudgetPolicy | None = None,
        closeout_max_chars: int = 1_200,
    ) -> None:
        self.client = client
        self.governor = TokenGovernor(budget_policy)
        self.lifecycle_policy = LifecyclePolicy()
        self.closeout_policy = CloseoutPolicy(max_chars=closeout_max_chars)

    async def bootstrap(
        self,
        *,
        query: str,
        scope: AgentScope,
        ledger: ContextLedger,
    ) -> BootstrapResult:
        knowledge_filters = scope.knowledge_filters()
        episodic_filters = scope.episodic_filters()
        policy = self.governor.policy
        knowledge_rows = await self.client.knowledge_search(
            query=query,
            limit=policy.max_bootstrap_knowledge,
            view="compact",
            **knowledge_filters,
        )
        episode_rows = await self.client.memory_search(
            query=query,
            limit=policy.max_bootstrap_episodes,
            view="compact",
            **episodic_filters,
        )
        knowledge_candidates = [
            RecallCandidate.from_mapping(row, kind=RecallKind.KNOWLEDGE)
            for row in knowledge_rows
        ]
        episode_candidates = [
            RecallCandidate.from_mapping(row, kind=RecallKind.EPISODE)
            for row in episode_rows
        ]
        knowledge_budget = max(1, (policy.bootstrap_tokens * 3) // 5)
        episode_budget = max(1, policy.bootstrap_tokens - knowledge_budget)
        knowledge_pack = self.governor.select(
            knowledge_candidates,
            budget_tokens=knowledge_budget,
            ledger=ledger,
            max_items=policy.max_bootstrap_knowledge,
            reason="session_bootstrap_knowledge",
        )
        episode_pack = self.governor.select(
            episode_candidates,
            budget_tokens=episode_budget,
            ledger=ledger,
            max_items=policy.max_bootstrap_episodes,
            reason="session_bootstrap_episode",
        )
        context = ContextPack(
            items=knowledge_pack.items + episode_pack.items,
            estimated_tokens=knowledge_pack.estimated_tokens + episode_pack.estimated_tokens,
            omitted_ids=knowledge_pack.omitted_ids + episode_pack.omitted_ids,
        )
        return BootstrapResult(context=context)

    async def recall(
        self,
        *,
        intent: TurnRecallIntent,
        scope: AgentScope,
        ledger: ContextLedger,
    ) -> ContextPack:
        operations = self.lifecycle_policy.recall_operations(intent)
        if not operations:
            return ContextPack(items=(), estimated_tokens=0)

        signature = self._recall_signature(intent, operations)
        if signature in ledger.recall_signatures and not intent.refresh:
            return ContextPack(items=(), estimated_tokens=0)
        ledger.recall_signatures.add(signature)

        candidates: list[RecallCandidate] = []
        knowledge_filters = scope.knowledge_filters()
        episodic_filters = scope.episodic_filters()
        if "knowledge_search" in operations:
            rows = await self.client.knowledge_search(
                query=intent.query,
                limit=3,
                view="compact",
                **knowledge_filters,
            )
            candidates.extend(
                RecallCandidate.from_mapping(row, kind=RecallKind.KNOWLEDGE) for row in rows
            )
        if "memory_search" in operations:
            rows = await self.client.memory_search(
                query=intent.query,
                limit=2,
                view="compact",
                **episodic_filters,
            )
            candidates.extend(
                RecallCandidate.from_mapping(row, kind=RecallKind.EPISODE) for row in rows
            )
        if "knowledge_timeline" in operations:
            if not intent.timeline_identity:
                raise ValueError("timeline_identity is required when need_timeline is true")
            rows = await self.client.knowledge_timeline(**intent.timeline_identity)
            candidates.extend(
                RecallCandidate.from_mapping(row, kind=RecallKind.KNOWLEDGE) for row in rows
            )

        return self.governor.select(
            candidates,
            budget_tokens=self.governor.policy.targeted_recall_tokens,
            ledger=ledger,
            max_items=5,
            reason="targeted_recall",
        )

    @staticmethod
    def _recall_signature(intent: TurnRecallIntent, operations: tuple[str, ...]) -> str:
        timeline = tuple(sorted((intent.timeline_identity or {}).items()))
        return repr((intent.query.strip(), operations, timeline))

    async def fetch_full(
        self,
        *,
        record_id: str,
        kind: RecallKind,
        ledger: ContextLedger,
    ) -> dict[str, Any] | None:
        if ledger.full_fetch_count >= self.governor.policy.full_record_limit:
            return None
        if record_id not in ledger.injected_ids:
            return None
        if kind is RecallKind.KNOWLEDGE:
            row = await self.client.knowledge_get(record_id=record_id)
        elif kind is RecallKind.EPISODE:
            row = await self.client.memory_get(record_id=record_id)
        else:
            return None
        if row is not None:
            ledger.full_fetch_count += 1
        return row

    async def close_session(
        self,
        *,
        scope: AgentScope,
        closeout: SessionCloseout,
        event_time: datetime,
    ) -> dict[str, Any]:
        content = self.closeout_policy.render(closeout)
        return await self.client.memory_store(
            content=content,
            session_id=scope.session_id,
            event_time=event_time,
            agent=scope.agent,
            project=scope.project,
            topic=scope.topic,
            source="agent_adapter_closeout",
        )
