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
    Observation,
    OutcomeMatch,
    PredictionDecision,
    PredictionIntent,
    RecallCandidate,
    RecallKind,
    SessionCloseout,
    TurnRecallIntent,
)
from cyberbrain.agent_adapter.policies import (
    CloseoutPolicy,
    LifecyclePolicy,
    OutcomeMatchPolicy,
    PredictionPolicy,
)


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
        self.prediction_policy = PredictionPolicy()
        self.outcome_match_policy = OutcomeMatchPolicy()

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
            context_session_id=scope.session_id,
            task_id=ledger.task_id or "session_bootstrap",
            **knowledge_filters,
        )
        episode_rows = await self.client.memory_search(
            query=query,
            limit=policy.max_bootstrap_episodes,
            view="compact",
            context_session_id=scope.session_id,
            task_id=ledger.task_id or "session_bootstrap",
            **episodic_filters,
        )
        knowledge_candidates = [
            RecallCandidate.from_mapping(row, kind=RecallKind.KNOWLEDGE) for row in knowledge_rows
        ]
        episode_candidates = [
            RecallCandidate.from_mapping(row, kind=RecallKind.EPISODE) for row in episode_rows
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
                context_session_id=scope.session_id,
                task_id=ledger.task_id or "targeted_recall",
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
                context_session_id=scope.session_id,
                task_id=ledger.task_id or "targeted_recall",
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

    async def record_prediction(
        self,
        *,
        intent: PredictionIntent,
        scope: AgentScope,
        strategy_tags: list[str] | None = None,
    ) -> tuple[PredictionDecision, dict[str, Any] | None]:
        decision = self.prediction_policy.decide(intent)
        if not decision.create:
            return decision, None

        payload: dict[str, Any] = {
            "expected_outcome": intent.expected_outcome,
            "confidence": intent.confidence,
            "session_id": scope.session_id,
            "event_time": intent.event_time,
            "action": intent.action,
            "agent": scope.agent,
            "project": scope.project,
            "topic": scope.topic,
        }
        if intent.correlation_id:
            payload["correlation_id"] = intent.correlation_id
        if strategy_tags:
            payload["strategy_tags"] = strategy_tags

        record = await self.client.prediction_record(**payload)
        return decision, record

    async def resolve_prediction(
        self,
        *,
        observation: Observation,
        scope: AgentScope,
    ) -> tuple[OutcomeMatch, dict[str, Any] | None]:
        if observation.prediction_id:
            record = await self.client.prediction_resolve(
                prediction_id=observation.prediction_id,
                observed_outcome=observation.observed_outcome,
                assessment=observation.assessment,
                event_time=observation.event_time,
            )
            return OutcomeMatch(observation.prediction_id, "direct_prediction_id"), record

        if hasattr(self.client, "prediction_pending_envelope"):
            envelope = await self.client.prediction_pending_envelope(
                session_id=scope.session_id,
                agent=scope.agent,
                project=scope.project,
                limit=20,
            )
            pending_items = list(envelope.get("items") or [])
            may_be_incomplete = envelope.get("may_be_incomplete") is not False
        else:
            pending_result = await self.client.prediction_pending(
                session_id=scope.session_id,
                agent=scope.agent,
                project=scope.project,
                limit=20,
            )
            if isinstance(pending_result, dict):
                pending_items = list(pending_result.get("items") or [])
                may_be_incomplete = pending_result.get("may_be_incomplete") is not False
            else:
                pending_items = list(pending_result)
                may_be_incomplete = True

        if observation.correlation_id and may_be_incomplete:
            return (
                OutcomeMatch(
                    None,
                    "incomplete_scan_cannot_verify_correlation_uniqueness",
                ),
                None,
            )

        match = self.outcome_match_policy.match(pending_items, observation)
        if match.prediction_id is None:
            return match, None

        record = await self.client.prediction_resolve(
            prediction_id=match.prediction_id,
            observed_outcome=observation.observed_outcome,
            assessment=observation.assessment,
            event_time=observation.event_time,
        )
        return match, record
