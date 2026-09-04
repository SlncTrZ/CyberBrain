# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    record_type: str
    content: str
    score: float | None
    event_time: datetime | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DreamCandidate:
    entity_name: str
    entity_type: str
    summary: str
    content: str
    evidence_ids: list[str]
    confidence: float
    classification: str
    negative_knowledge: bool = False
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DreamReasoningRequest:
    request_id: str
    session_id: str
    focal_topics: list[str]
    session_start: datetime
    session_end: datetime
    evidence_by_topic: dict[str, list[EvidenceItem]]
    instructions_version: str = "1"


@dataclass(frozen=True)
class DreamReasoningResult:
    request_id: str
    candidates: list[DreamCandidate]
    notes: list[str] = field(default_factory=list)


class ReasoningTaskKind(StrEnum):
    CURRENT_STATE = "current_state"
    SUPERSEDED_OR_REMOVED = "superseded_or_removed"
    DURABLE_LESSON = "durable_lesson"
    CAVEAT = "caveat"


@dataclass(frozen=True)
class ReasoningTask:
    task_id: str
    request_id: str
    topic: str
    kind: ReasoningTaskKind
    instruction: str
    evidence: list[EvidenceItem]


@dataclass(frozen=True)
class ReasoningClaim:
    claim: str
    evidence_ids: list[str]
    confidence: float


@dataclass(frozen=True)
class ReasoningTaskResult:
    task_id: str
    claims: list[ReasoningClaim]


class MicroReasoner(Protocol):
    def reason_task(self, task: ReasoningTask) -> ReasoningTaskResult: ...


class DreamReasoner(Protocol):
    def reason(self, request: DreamReasoningRequest) -> DreamReasoningResult: ...
