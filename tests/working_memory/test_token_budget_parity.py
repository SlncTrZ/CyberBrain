# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from cyberbrain.agent_adapter import TokenBudgetPolicy, TokenGovernor
from cyberbrain.core.token_budget import DeterministicTokenCounter


def test_agent_adapter_and_working_memory_share_token_estimation_semantics() -> None:
    text = "bounded context " * 17
    governor = TokenGovernor(TokenBudgetPolicy(chars_per_token=3))
    counter = DeterministicTokenCounter(chars_per_token=3)

    assert governor.estimate_tokens(text) == counter.estimate_tokens(text)
    assert governor.clip_to_tokens(text, 19) == counter.clip_to_tokens(text, 19)
