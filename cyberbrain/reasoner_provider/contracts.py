# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Classification = Literal[
    "new_knowledge",
    "evolution",
    "context_dependent",
    "contradiction",
    "rejected_approach",
    "insufficient_evidence",
]

ReasoningTaskKindValue = Literal[
    "current_state",
    "superseded_or_removed",
    "durable_lesson",
    "caveat",
]


class ReasonerEvidence(BaseModel):
    id: str
    record_type: str
    content: str
    score: float | None = None
    event_time: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReasonRequest(BaseModel):
    request_id: str
    session_id: str
    focal_topics: list[str]
    session_start: datetime
    session_end: datetime
    instructions_version: str = "1"
    evidence_by_topic: dict[str, list[ReasonerEvidence]]


class ReasonCandidate(BaseModel):
    entity_name: str
    entity_type: str
    summary: str
    content: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    classification: Classification
    negative_knowledge: bool = False
    context: dict[str, Any] = Field(default_factory=dict)


class ReasonResult(BaseModel):
    request_id: str
    candidates: list[ReasonCandidate] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ReasonTaskRequest(BaseModel):
    task_id: str
    request_id: str
    topic: str
    kind: ReasoningTaskKindValue
    instruction: str
    evidence: list[ReasonerEvidence]


class ReasonTaskClaim(BaseModel):
    claim: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class ReasonTaskResult(BaseModel):
    task_id: str
    claims: list[ReasonTaskClaim] = Field(default_factory=list)


def validate_result_against_request(request: ReasonRequest, result: ReasonResult) -> ReasonResult:
    if result.request_id != request.request_id:
        raise ValueError("reasoner result request_id does not match request")

    allowed_evidence_ids = {
        item.id
        for items in request.evidence_by_topic.values()
        for item in items
    }
    for candidate in result.candidates:
        unknown = sorted(set(candidate.evidence_ids) - allowed_evidence_ids)
        if unknown:
            raise ValueError(f"reasoner result contains unknown evidence ids: {unknown}")
    return result


def validate_task_result(
    request: ReasonTaskRequest,
    result: ReasonTaskResult,
) -> ReasonTaskResult:
    if result.task_id != request.task_id:
        raise ValueError("micro reasoner result task_id does not match request")

    allowed_evidence_ids = {item.id for item in request.evidence}
    for claim in result.claims:
        unknown = sorted(set(claim.evidence_ids) - allowed_evidence_ids)
        if unknown:
            raise ValueError(f"micro reasoner result contains unknown evidence ids: {unknown}")
    return result
