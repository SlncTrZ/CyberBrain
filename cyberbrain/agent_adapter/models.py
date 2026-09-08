# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class RecallKind(StrEnum):
    KNOWLEDGE = "knowledge"
    EPISODE = "episode"


class Consequence(StrEnum):
    TRIVIAL = "trivial"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class AgentScope:
    session_id: str
    agent: str | None = None
    project: str | None = None
    topic: str | None = None

    def knowledge_filters(self) -> dict[str, str]:
        return {
            key: value
            for key, value in {"project": self.project, "topic": self.topic}.items()
            if value is not None
        }

    def episodic_filters(self) -> dict[str, str]:
        return {
            key: value
            for key, value in {
                "agent": self.agent,
                "project": self.project,
                "topic": self.topic,
            }.items()
            if value is not None
        }


@dataclass(frozen=True, slots=True)
class RecallCandidate:
    record_id: str
    kind: RecallKind
    text: str
    score: float | None = None
    text_source: str | None = None
    content_chars: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, row: dict[str, Any], *, kind: RecallKind) -> RecallCandidate:
        record_id = str(row.get("id") or "").strip()
        if not record_id:
            raise ValueError("recall row is missing id")
        text = str(
            row.get("recall_text")
            or row.get("summary")
            or row.get("content")
            or row.get("expected_outcome")
            or ""
        ).strip()
        metadata = {
            key: value
            for key, value in row.items()
            if key
            not in {
                "id",
                "score",
                "recall_text",
                "summary",
                "content",
                "expected_outcome",
                "recall_text_source",
                "content_chars",
            }
        }
        score = row.get("score")
        return cls(
            record_id=record_id,
            kind=kind,
            text=text,
            score=float(score) if score is not None else None,
            text_source=(
                str(row.get("recall_text_source"))
                if row.get("recall_text_source")
                else None
            ),
            content_chars=(
                int(row["content_chars"])
                if row.get("content_chars") is not None
                else None
            ),
            metadata=metadata,
        )


@dataclass(frozen=True, slots=True)
class ContextItem:
    record_id: str
    kind: RecallKind
    text: str
    estimated_tokens: int
    reason: str


@dataclass(frozen=True, slots=True)
class ContextPack:
    items: tuple[ContextItem, ...]
    estimated_tokens: int
    omitted_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class ContextLedger:
    session_id: str
    task_id: str | None = None
    injected_ids: set[str] = field(default_factory=set)
    recall_signatures: set[str] = field(default_factory=set)
    consumed_tokens: int = 0
    full_fetch_count: int = 0

    def mark_injected(self, item: ContextItem) -> None:
        self.injected_ids.add(item.record_id)
        self.consumed_tokens += item.estimated_tokens


@dataclass(frozen=True, slots=True)
class TurnRecallIntent:
    query: str
    need_knowledge: bool = False
    need_history: bool = False
    need_timeline: bool = False
    timeline_identity: dict[str, str] | None = None
    refresh: bool = False


@dataclass(frozen=True, slots=True)
class PredictionIntent:
    expected_outcome: str
    confidence: float
    event_time: datetime
    outcome_known: bool
    observable_later: bool
    resolvable_with_evidence: bool
    consequence: Consequence
    action: str | None = None
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class PredictionDecision:
    create: bool
    reason_code: str


@dataclass(frozen=True, slots=True)
class Observation:
    observed_outcome: str
    assessment: str
    event_time: datetime
    prediction_id: str | None = None
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class OutcomeMatch:
    prediction_id: str | None
    reason_code: str


@dataclass(frozen=True, slots=True)
class SessionCloseout:
    goal: str
    actions: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    outcomes: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    identifiers: tuple[str, ...] = ()
