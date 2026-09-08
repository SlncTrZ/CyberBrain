# SPDX-License-Identifier: MPL-2.0
"""M5 selection policy: relevance → Salience → dedupe → budget."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from cyberbrain.core.token_budget import DeterministicTokenCounter
from cyberbrain.salience import SalienceAdvisor, SalienceCandidate

from .models import (
    WorkingMemoryCandidate,
    WorkingMemoryIdentity,
    WorkingMemoryItem,
    WorkingMemorySelectionReport,
)


@dataclass(frozen=True, slots=True)
class WorkingMemoryPolicy:
    max_items: int = 12
    max_tokens: int = 1_200
    max_item_tokens: int = 240
    max_candidates: int = 64
    minimum_task_relevance: float = 0.20
    ttl_seconds: int = 3_600

    def __post_init__(self) -> None:
        for name in ("max_items", "max_tokens", "max_item_tokens", "max_candidates", "ttl_seconds"):
            if getattr(self, name) <= 0:
                raise ValueError(f"working memory {name} must be positive")
        if self.max_item_tokens > self.max_tokens:
            raise ValueError("working memory max_item_tokens must not exceed max_tokens")
        if self.max_items > self.max_candidates:
            raise ValueError("working memory max_items must not exceed max_candidates")
        if not 0 <= self.minimum_task_relevance <= 1:
            raise ValueError("working memory minimum_task_relevance must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class _RankedCandidate:
    candidate: WorkingMemoryCandidate
    input_index: int
    salience_score: float
    salience_reasons: tuple


class WorkingMemorySelector:
    def __init__(
        self,
        policy: WorkingMemoryPolicy | None = None,
        *,
        governor: DeterministicTokenCounter | None = None,
        salience_advisor: SalienceAdvisor | None = None,
    ) -> None:
        self.policy = policy or WorkingMemoryPolicy()
        self.governor = governor or DeterministicTokenCounter()
        self.salience_advisor = salience_advisor or SalienceAdvisor()

    def select(
        self,
        identity: WorkingMemoryIdentity,
        candidates: list[WorkingMemoryCandidate] | tuple[WorkingMemoryCandidate, ...],
    ) -> tuple[tuple[WorkingMemoryItem, ...], WorkingMemorySelectionReport]:
        rows = tuple(candidates)
        if len(rows) > self.policy.max_candidates:
            raise ValueError("working memory candidate count exceeds max_candidates")
        candidate_ids = [row.candidate_id for row in rows]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("working memory candidate IDs must be unique")
        mismatched = [row.candidate_id for row in rows if row.identity != identity]
        if mismatched:
            raise ValueError(
                "working memory candidate identity must match exact working set identity"
            )

        relevant = tuple(
            row
            for row in rows
            if row.task_relevance.score >= self.policy.minimum_task_relevance
        )
        advisory = self.salience_advisor.assess(
            [
                SalienceCandidate(
                    candidate_id=row.candidate_id,
                    scope_marker=identity.scope_marker,
                    signals=row.salience,
                )
                for row in relevant
            ]
        )
        assessments = {
            row.candidate_id: row.assessment for row in advisory.assessments
        }
        ranked = [
            _RankedCandidate(
                candidate=row,
                input_index=index,
                salience_score=assessments[row.candidate_id].score,
                salience_reasons=assessments[row.candidate_id].reason_codes,
            )
            for index, row in enumerate(relevant)
        ]
        ranked.sort(
            key=lambda item: (
                -item.candidate.task_relevance.score,
                -item.salience_score,
                item.input_index,
            )
        )

        unique: list[_RankedCandidate] = []
        seen_dedupe: set[str] = set()
        duplicate_ids: list[str] = []
        for row in ranked:
            key = row.candidate.dedupe_key
            if key in seen_dedupe:
                duplicate_ids.append(row.candidate.candidate_id)
                continue
            seen_dedupe.add(key)
            unique.append(row)

        remaining = self.policy.max_tokens
        selected: list[WorkingMemoryItem] = []
        budget_omitted: list[str] = []
        for row in unique:
            if len(selected) >= self.policy.max_items or remaining <= 0:
                budget_omitted.append(row.candidate.candidate_id)
                continue
            item_budget = min(self.policy.max_item_tokens, remaining)
            text = self.governor.clip_to_tokens(row.candidate.text, item_budget)
            tokens = self.governor.estimate_tokens(text)
            if not text or tokens <= 0:
                budget_omitted.append(row.candidate.candidate_id)
                continue
            fingerprint = hashlib.sha256(
                f"{row.candidate.kind.value}|{row.candidate.reference_id or ''}|{text}".encode()
            ).hexdigest()[:24]
            selected.append(
                WorkingMemoryItem(
                    candidate_id=row.candidate.candidate_id,
                    kind=row.candidate.kind,
                    text=text,
                    estimated_tokens=tokens,
                    task_relevance=row.candidate.task_relevance.score,
                    task_relevance_reasons=row.candidate.task_relevance.reason_codes,
                    salience_score=row.salience_score,
                    salience_reasons=row.salience_reasons,
                    reference_id=row.candidate.reference_id,
                    source_record_id=row.candidate.source_record_id,
                    content_fingerprint=fingerprint,
                )
            )
            remaining -= tokens

        irrelevant_ids = [
            row.candidate_id
            for row in rows
            if row.task_relevance.score < self.policy.minimum_task_relevance
        ]
        omitted = tuple(irrelevant_ids + duplicate_ids + budget_omitted)
        report = WorkingMemorySelectionReport(
            input_count=len(rows),
            relevant_count=len(relevant),
            duplicate_suppressed_count=len(duplicate_ids),
            budget_omitted_count=len(budget_omitted),
            selected_count=len(selected),
            selected_tokens=sum(item.estimated_tokens for item in selected),
            omitted_candidate_ids=omitted,
        )
        return tuple(selected), report
