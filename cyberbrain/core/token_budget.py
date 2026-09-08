# SPDX-License-Identifier: MPL-2.0
"""Shared deterministic token-estimation and clipping primitive."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeterministicTokenCounter:
    chars_per_token: int = 4

    def __post_init__(self) -> None:
        if self.chars_per_token <= 0:
            raise ValueError("chars_per_token must be positive")

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        chars = len(text)
        return max(1, (chars + self.chars_per_token - 1) // self.chars_per_token)

    def clip_to_tokens(self, text: str, budget_tokens: int) -> str:
        if budget_tokens <= 0:
            return ""
        max_chars = budget_tokens * self.chars_per_token
        if len(text) <= max_chars:
            return text
        if max_chars <= 1:
            return text[:max_chars]
        return text[: max_chars - 1].rstrip() + "…"
