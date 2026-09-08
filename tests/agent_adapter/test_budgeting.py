# SPDX-License-Identifier: MPL-2.0

from cyberbrain.agent_adapter import ContextLedger, RecallKind, TokenBudgetPolicy, TokenGovernor
from cyberbrain.agent_adapter.models import RecallCandidate


def test_token_governor_clips_deterministically_to_budget() -> None:
    governor = TokenGovernor(TokenBudgetPolicy(chars_per_token=4))
    ledger = ContextLedger(session_id="s1")
    candidate = RecallCandidate(record_id="k1", kind=RecallKind.KNOWLEDGE, text="x" * 100)

    pack = governor.select(
        [candidate],
        budget_tokens=10,
        ledger=ledger,
        max_items=1,
        reason="test",
    )

    assert pack.estimated_tokens == 10
    assert len(pack.items) == 1
    assert len(pack.items[0].text) <= 40
    assert ledger.consumed_tokens == 10


def test_token_governor_suppresses_duplicate_record_ids() -> None:
    governor = TokenGovernor()
    ledger = ContextLedger(session_id="s1", injected_ids={"k1"})
    candidates = [
        RecallCandidate(record_id="k1", kind=RecallKind.KNOWLEDGE, text="duplicate"),
        RecallCandidate(record_id="k2", kind=RecallKind.KNOWLEDGE, text="new"),
    ]

    pack = governor.select(
        candidates,
        budget_tokens=100,
        ledger=ledger,
        max_items=2,
        reason="test",
    )

    assert [item.record_id for item in pack.items] == ["k2"]
    assert "k1" in pack.omitted_ids
