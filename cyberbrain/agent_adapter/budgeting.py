# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass

from cyberbrain.agent_adapter.models import ContextItem, ContextLedger, ContextPack, RecallCandidate


@dataclass(frozen=True, slots=True)
class TokenBudgetPolicy:
    bootstrap_tokens: int = 1_000
    targeted_recall_tokens: int = 500
    full_record_limit: int = 1
    chars_per_token: int = 4
    max_bootstrap_knowledge: int = 3
    max_bootstrap_episodes: int = 2
    max_pending_predictions: int = 3

    def __post_init__(self) -> None:
        for name in (
            "bootstrap_tokens",
            "targeted_recall_tokens",
            "full_record_limit",
            "chars_per_token",
            "max_bootstrap_knowledge",
            "max_bootstrap_episodes",
            "max_pending_predictions",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")


class TokenGovernor:
    def __init__(self, policy: TokenBudgetPolicy | None = None) -> None:
        self.policy = policy or TokenBudgetPolicy()

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        chars = len(text)
        return max(1, (chars + self.policy.chars_per_token - 1) // self.policy.chars_per_token)

    def clip_to_tokens(self, text: str, budget_tokens: int) -> str:
        if budget_tokens <= 0:
            return ""
        max_chars = budget_tokens * self.policy.chars_per_token
        if len(text) <= max_chars:
            return text
        if max_chars <= 1:
            return text[:max_chars]
        return text[: max_chars - 1].rstrip() + "…"

    def select(
        self,
        candidates: list[RecallCandidate],
        *,
        budget_tokens: int,
        ledger: ContextLedger,
        max_items: int,
        reason: str,
    ) -> ContextPack:
        remaining = budget_tokens
        items: list[ContextItem] = []
        omitted: list[str] = []

        for candidate in candidates:
            if candidate.record_id in ledger.injected_ids:
                omitted.append(candidate.record_id)
                continue
            if len(items) >= max_items:
                omitted.append(candidate.record_id)
                continue
            if remaining <= 0:
                omitted.append(candidate.record_id)
                continue

            clipped = self.clip_to_tokens(candidate.text, remaining)
            estimated = self.estimate_tokens(clipped)
            if not clipped or estimated <= 0:
                omitted.append(candidate.record_id)
                continue

            item = ContextItem(
                record_id=candidate.record_id,
                kind=candidate.kind,
                text=clipped,
                estimated_tokens=estimated,
                reason=reason,
            )
            items.append(item)
            ledger.mark_injected(item)
            remaining -= estimated

        return ContextPack(
            items=tuple(items),
            estimated_tokens=sum(item.estimated_tokens for item in items),
            omitted_ids=tuple(omitted),
        )
