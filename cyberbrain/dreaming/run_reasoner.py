# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from cyberbrain.dreaming.orchestration import MultipassDreamReasoner
from cyberbrain.dreaming.reason_task_inbox import DreamReasonTaskInbox
from cyberbrain.dreaming.reasoner import (
    DreamReasoner,
    DreamReasoningRequest,
    DreamReasoningResult,
    EvidenceItem,
    MicroReasoner,
    ReasoningClaim,
    ReasoningTask,
    ReasoningTaskResult,
)


class MCPFirstDreamReasoner(DreamReasoner):
    """Run-level Dream reasoner: MCP inbox first, fallback router only for unfinished tasks."""

    def __init__(
        self,
        *,
        multipass: MultipassDreamReasoner,
        inbox: DreamReasonTaskInbox,
        fallback_micro_reasoner: MicroReasoner,
        wait_seconds: float,
        poll_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if wait_seconds < 0:
            raise ValueError("wait_seconds must be >= 0")
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be > 0")
        self._multipass = multipass
        self._inbox = inbox
        self._fallback = fallback_micro_reasoner
        self._wait_seconds = float(wait_seconds)
        self._poll_seconds = float(poll_seconds)
        self._sleep = sleep
        self._monotonic = monotonic

    def reason(self, request: DreamReasoningRequest) -> DreamReasoningResult:
        tasks = self._multipass.build_tasks(request)
        self._inbox.register_run(
            request_id=request.request_id,
            request=self._serialize_request(request),
            tasks=[self._serialize_task(task) for task in tasks],
            wait_seconds=self._wait_seconds,
        )

        deadline = self._monotonic() + self._wait_seconds
        while tasks and self._monotonic() < deadline:
            if self._all_completed(request.request_id):
                break
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                break
            self._sleep(min(self._poll_seconds, remaining))

        results = [self._resolve_task(task) for task in tasks]
        return self._multipass.assemble(request, tasks=tasks, results=results)

    def _all_completed(self, request_id: str) -> bool:
        states = self._inbox.run_tasks(request_id)
        return bool(states) and all(state.status == "completed" for state in states)

    def _resolve_task(self, task: ReasoningTask) -> ReasoningTaskResult:
        state = self._inbox.task_state(task.task_id)
        if state is None:
            raise RuntimeError(f"reason task disappeared from inbox: {task.task_id}")

        if state.status == "completed" and state.result is not None:
            return self._parse_result(state.result)

        fallback_result = self._fallback.reason_task(task)
        winner = self._inbox.complete_fallback(
            task_id=task.task_id,
            result=self._serialize_result(fallback_result),
            route="fallback-router",
        )
        return self._parse_result(winner)

    @staticmethod
    def _serialize_request(request: DreamReasoningRequest) -> dict[str, Any]:
        return {
            "request_id": request.request_id,
            "session_id": request.session_id,
            "focal_topics": list(request.focal_topics),
            "session_start": request.session_start.isoformat(),
            "session_end": request.session_end.isoformat(),
            "instructions_version": request.instructions_version,
            "evidence_by_topic": {
                topic: [
                    MCPFirstDreamReasoner._serialize_evidence(item)
                    for item in evidence
                ]
                for topic, evidence in request.evidence_by_topic.items()
            },
        }

    @staticmethod
    def _serialize_task(task: ReasoningTask) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "request_id": task.request_id,
            "topic": task.topic,
            "kind": task.kind.value,
            "instruction": task.instruction,
            "evidence": [
                MCPFirstDreamReasoner._serialize_evidence(item)
                for item in task.evidence
            ],
        }

    @staticmethod
    def _serialize_evidence(item: EvidenceItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "record_type": item.record_type,
            "content": item.content,
            "score": item.score,
            "event_time": item.event_time.isoformat() if item.event_time else None,
            "metadata": dict(item.metadata),
        }

    @staticmethod
    def _serialize_result(result: ReasoningTaskResult) -> dict[str, Any]:
        return {
            "task_id": result.task_id,
            "claims": [
                {
                    "claim": claim.claim,
                    "evidence_ids": list(claim.evidence_ids),
                    "confidence": claim.confidence,
                }
                for claim in result.claims
            ],
        }

    @staticmethod
    def _parse_result(raw: dict[str, Any]) -> ReasoningTaskResult:
        return ReasoningTaskResult(
            task_id=str(raw["task_id"]),
            claims=[
                ReasoningClaim(
                    claim=str(item["claim"]),
                    evidence_ids=[str(value) for value in item.get("evidence_ids", [])],
                    confidence=float(item["confidence"]),
                )
                for item in raw.get("claims", [])
            ],
        )
