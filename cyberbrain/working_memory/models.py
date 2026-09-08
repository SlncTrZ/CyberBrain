# SPDX-License-Identifier: MPL-2.0
"""Immutable M5 Working Memory domain contracts."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from cyberbrain.salience import SalienceInput, SalienceReasonCode

WORKING_MEMORY_VERSION = "working-memory-v1"
_SPACE_RE = re.compile(r"\s+")


class WorkingMemoryItemKind(StrEnum):
    GOAL = "goal"
    SUBGOAL = "subgoal"
    ASSUMPTION = "assumption"
    HYPOTHESIS = "hypothesis"
    EVIDENCE = "evidence"
    CONCEPT_REFERENCE = "concept_reference"
    BLOCKER = "blocker"
    OPEN_QUESTION = "open_question"
    RECENT_DECISION = "recent_decision"
    SELECTED_MEMORY_REFERENCE = "selected_memory_reference"


@dataclass(frozen=True, slots=True)
class WorkingMemoryIdentity:
    """Exact transient-state identity. Scope is never inferred or widened."""

    scope_marker: str
    session_id: str
    task_id: str

    def __post_init__(self) -> None:
        for name in ("scope_marker", "session_id", "task_id"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"working memory {name} must not be empty")
            object.__setattr__(self, name, value)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.scope_marker, self.session_id, self.task_id)


@dataclass(frozen=True, slots=True)
class TaskRelevance:
    """Explicit task relevance supplied by an already-authorized task layer."""

    score: float
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.score, bool) or not isinstance(self.score, int | float):
            raise ValueError("task relevance score must be a finite number")
        normalized = float(self.score)
        if not math.isfinite(normalized) or not 0 <= normalized <= 1:
            raise ValueError("task relevance score must be within [0, 1]")
        object.__setattr__(self, "score", normalized)
        cleaned = tuple(code.strip() for code in self.reason_codes if code.strip())
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("task relevance reason codes must be unique")
        object.__setattr__(self, "reason_codes", cleaned)


@dataclass(frozen=True, slots=True)
class WorkingMemoryCandidate:
    candidate_id: str
    identity: WorkingMemoryIdentity
    kind: WorkingMemoryItemKind
    text: str
    task_relevance: TaskRelevance
    salience: SalienceInput = field(default_factory=SalienceInput)
    reference_id: str | None = None
    source_record_id: str | None = None

    def __post_init__(self) -> None:
        candidate_id = self.candidate_id.strip()
        text = self.text.strip()
        if not candidate_id:
            raise ValueError("working memory candidate_id must not be empty")
        if not text:
            raise ValueError("working memory candidate text must not be empty")
        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "text", text)
        for name in ("reference_id", "source_record_id"):
            value = getattr(self, name)
            if value is None:
                continue
            cleaned = value.strip()
            object.__setattr__(self, name, cleaned or None)
        if self.kind in {
            WorkingMemoryItemKind.CONCEPT_REFERENCE,
            WorkingMemoryItemKind.SELECTED_MEMORY_REFERENCE,
        } and not self.reference_id:
            raise ValueError(f"{self.kind.value} requires reference_id")

    @property
    def dedupe_key(self) -> str:
        if self.reference_id:
            return f"ref:{self.kind.value}:{self.reference_id}"
        if self.source_record_id:
            return f"source:{self.source_record_id}"
        normalized = _SPACE_RE.sub(" ", self.text).strip().casefold()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
        return f"text:{digest}"


@dataclass(frozen=True, slots=True)
class WorkingMemoryItem:
    candidate_id: str
    kind: WorkingMemoryItemKind
    text: str
    estimated_tokens: int
    task_relevance: float
    task_relevance_reasons: tuple[str, ...]
    salience_score: float
    salience_reasons: tuple[SalienceReasonCode, ...]
    reference_id: str | None
    source_record_id: str | None
    content_fingerprint: str

    def __post_init__(self) -> None:
        if self.estimated_tokens <= 0:
            raise ValueError("working memory item estimated_tokens must be positive")
        if not self.content_fingerprint.strip():
            raise ValueError("working memory item content_fingerprint must not be empty")


@dataclass(frozen=True, slots=True)
class WorkingMemorySelectionReport:
    input_count: int
    relevant_count: int
    duplicate_suppressed_count: int
    budget_omitted_count: int
    selected_count: int
    selected_tokens: int
    omitted_candidate_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkingMemorySnapshot:
    identity: WorkingMemoryIdentity
    revision: int
    items: tuple[WorkingMemoryItem, ...]
    estimated_tokens: int
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    selection: WorkingMemorySelectionReport
    version: str = WORKING_MEMORY_VERSION

    def __post_init__(self) -> None:
        if self.revision <= 0:
            raise ValueError("working memory revision must be positive")
        if self.estimated_tokens != sum(item.estimated_tokens for item in self.items):
            raise ValueError("working memory snapshot token total is inconsistent")
        if self.expires_at <= self.updated_at:
            raise ValueError("working memory expires_at must be after updated_at")
        ids = [item.candidate_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("working memory snapshot candidate IDs must be unique")


@dataclass(slots=True)
class WorkingMemoryEmissionLedger:
    identity: WorkingMemoryIdentity
    emitted_fingerprints: dict[str, str] = field(default_factory=dict)
    emitted_tokens: int = 0


@dataclass(frozen=True, slots=True)
class WorkingMemoryEmission:
    identity: WorkingMemoryIdentity
    revision: int
    items: tuple[WorkingMemoryItem, ...]
    estimated_tokens: int
    repeated_suppressed_count: int


@dataclass(frozen=True, slots=True)
class WorkingMemoryCloseout:
    identity: WorkingMemoryIdentity
    existed: bool
    final_revision: int | None
    final_item_count: int
    final_estimated_tokens: int
