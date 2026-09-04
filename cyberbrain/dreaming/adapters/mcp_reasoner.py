# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from typing import Any, Protocol

from cyberbrain.dreaming.reasoner import (
    DreamCandidate,
    DreamReasoner,
    DreamReasoningRequest,
    DreamReasoningResult,
    EvidenceItem,
)


class ReasonerToolInvoker(Protocol):
    def invoke(self, *, tool: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class MCPReasoner(DreamReasoner):
    def __init__(self, *, invoker: ReasonerToolInvoker, tool: str) -> None:
        self._invoker = invoker
        self._tool = tool

    def reason(self, request: DreamReasoningRequest) -> DreamReasoningResult:
        raw = self._invoker.invoke(
            tool=self._tool,
            arguments=self._serialize_request(request),
        )
        return self._parse_result(raw)

    @staticmethod
    def _serialize_request(request: DreamReasoningRequest) -> dict[str, Any]:
        return {
            "request_id": request.request_id,
            "session_id": request.session_id,
            "focal_topics": request.focal_topics,
            "session_start": request.session_start.isoformat(),
            "session_end": request.session_end.isoformat(),
            "instructions_version": request.instructions_version,
            "evidence_by_topic": {
                topic: [MCPReasoner._serialize_evidence(item) for item in items]
                for topic, items in request.evidence_by_topic.items()
            },
        }

    @staticmethod
    def _serialize_evidence(item: EvidenceItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "record_type": item.record_type,
            "content": item.content,
            "score": item.score,
            "event_time": item.event_time.isoformat() if item.event_time else None,
            "metadata": item.metadata,
        }

    @staticmethod
    def _parse_result(raw: dict[str, Any]) -> DreamReasoningResult:
        request_id = str(raw.get("request_id", "")).strip()
        if not request_id:
            raise ValueError("reasoner result is missing request_id")

        candidates_raw = raw.get("candidates")
        if not isinstance(candidates_raw, list):
            raise ValueError("reasoner result candidates must be a list")

        candidates: list[DreamCandidate] = []
        for item in candidates_raw:
            if not isinstance(item, dict):
                raise ValueError("reasoner candidate must be an object")
            candidates.append(
                DreamCandidate(
                    entity_name=str(item["entity_name"]),
                    entity_type=str(item["entity_type"]),
                    summary=str(item["summary"]),
                    content=str(item["content"]),
                    evidence_ids=[str(value) for value in item.get("evidence_ids", [])],
                    confidence=float(item["confidence"]),
                    classification=str(item["classification"]),
                    negative_knowledge=bool(item.get("negative_knowledge", False)),
                    context=dict(item.get("context") or {}),
                )
            )

        notes_raw = raw.get("notes", [])
        if not isinstance(notes_raw, list):
            raise ValueError("reasoner result notes must be a list")

        return DreamReasoningResult(
            request_id=request_id,
            candidates=candidates,
            notes=[str(note) for note in notes_raw],
        )
