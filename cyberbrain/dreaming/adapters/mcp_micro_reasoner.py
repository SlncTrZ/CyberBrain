# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from typing import Any, Protocol

from cyberbrain.dreaming.reasoner import (
    EvidenceItem,
    MicroReasoner,
    ReasoningClaim,
    ReasoningTask,
    ReasoningTaskResult,
)


class MicroReasonerToolInvoker(Protocol):
    def invoke(self, *, tool: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class MCPMicroReasoner(MicroReasoner):
    """MCP-backed micro reasoner for the canonical multipass Dreaming flow."""

    def __init__(self, *, invoker: MicroReasonerToolInvoker, tool: str) -> None:
        self._invoker = invoker
        self._tool = tool

    def reason_task(self, task: ReasoningTask) -> ReasoningTaskResult:
        raw = self._invoker.invoke(
            tool=self._tool,
            arguments=self._serialize_task(task),
        )
        return self._parse_result(raw)

    @staticmethod
    def _serialize_task(task: ReasoningTask) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "request_id": task.request_id,
            "topic": task.topic,
            "kind": task.kind.value,
            "instruction": task.instruction,
            "evidence": [MCPMicroReasoner._serialize_evidence(item) for item in task.evidence],
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
    def _parse_result(raw: dict[str, Any]) -> ReasoningTaskResult:
        task_id = str(raw.get("task_id", "")).strip()
        if not task_id:
            raise ValueError("micro reasoner result is missing task_id")

        claims_raw = raw.get("claims")
        if not isinstance(claims_raw, list):
            raise ValueError("micro reasoner result claims must be a list")

        claims: list[ReasoningClaim] = []
        for item in claims_raw:
            if not isinstance(item, dict):
                raise ValueError("micro reasoner claim must be an object")
            claims.append(
                ReasoningClaim(
                    claim=str(item["claim"]),
                    evidence_ids=[str(value) for value in item.get("evidence_ids", [])],
                    confidence=float(item["confidence"]),
                )
            )

        return ReasoningTaskResult(task_id=task_id, claims=claims)
