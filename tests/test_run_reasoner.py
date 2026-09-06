# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cyberbrain.dreaming.orchestration import MultipassDreamReasoner
from cyberbrain.dreaming.reason_task_inbox import DreamReasonTaskInbox
from cyberbrain.dreaming.reasoner import (
    DreamReasoningRequest,
    EvidenceItem,
    ReasoningClaim,
    ReasoningTaskResult,
)
from cyberbrain.dreaming.run_reasoner import MCPFirstDreamReasoner


class TrackingFallback:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def reason_task(self, task):  # noqa: ANN001
        self.calls.append(task.task_id)
        return ReasoningTaskResult(
            task_id=task.task_id,
            claims=[
                ReasoningClaim(
                    claim=f"Fallback fact for {task.kind.value}",
                    evidence_ids=[item.id for item in task.evidence],
                    confidence=0.8,
                )
            ],
        )


def _request() -> DreamReasoningRequest:
    now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    return DreamReasoningRequest(
        request_id="run-level-1",
        session_id="session-1",
        focal_topics=["routing"],
        session_start=now - timedelta(hours=1),
        session_end=now,
        evidence_by_topic={
            "routing": [
                EvidenceItem(
                    id="e1",
                    record_type="knowledge",
                    content="MCP is the primary Dream Reasoner route.",
                    score=0.99,
                    event_time=now - timedelta(minutes=20),
                    metadata={"verification": "user_confirmed"},
                ),
                EvidenceItem(
                    id="e2",
                    record_type="knowledge",
                    content="9router is the fallback engine after MCP.",
                    score=0.95,
                    event_time=now - timedelta(minutes=10),
                    metadata={"verification": "tested"},
                ),
            ]
        },
    )


def _build(tmp_path):
    inbox = DreamReasonTaskInbox(tmp_path / "reason.sqlite")
    fallback = TrackingFallback()
    multipass = MultipassDreamReasoner(micro_reasoner=fallback)
    reasoner = MCPFirstDreamReasoner(
        multipass=multipass,
        inbox=inbox,
        fallback_micro_reasoner=fallback,
        wait_seconds=0,
    )
    return inbox, fallback, multipass, reasoner


def _complete_as_mcp(inbox, task) -> None:  # noqa: ANN001
    payload = MCPFirstDreamReasoner._serialize_task(task)
    inbox.publish(payload, wait_seconds=60)
    lease = inbox.claim_next(claimed_by="chatgpt:test", lease_seconds=60)
    assert lease is not None
    assert lease.task["task_id"] == task.task_id
    inbox.submit(
        task_id=task.task_id,
        claim_token=lease.claim_token,
        claims=[
            {
                "claim": f"MCP fact for {task.kind.value}",
                "evidence_ids": [item.id for item in task.evidence],
                "confidence": 0.99,
            }
        ],
    )


def test_run_level_reasoner_uses_mcp_results_before_fallback(tmp_path) -> None:
    inbox, fallback, multipass, reasoner = _build(tmp_path)
    request = _request()
    tasks = multipass.build_tasks(request)
    assert len(tasks) >= 2
    _complete_as_mcp(inbox, tasks[0])

    result = reasoner.reason(request)

    assert result.request_id == request.request_id
    assert tasks[0].task_id not in fallback.calls
    assert set(fallback.calls) == {task.task_id for task in tasks[1:]}
    states = inbox.run_tasks(request.request_id)
    routes = {state.task["task_id"]: state.route for state in states}
    assert routes[tasks[0].task_id] == "mcp"
    assert all(routes[task.task_id] == "fallback-router" for task in tasks[1:])
    assert len(result.candidates) == len(tasks)


def test_run_level_reasoner_skips_fallback_when_mcp_completed_every_task(tmp_path) -> None:
    inbox, fallback, multipass, reasoner = _build(tmp_path)
    request = _request()
    tasks = multipass.build_tasks(request)
    for task in tasks:
        _complete_as_mcp(inbox, task)

    result = reasoner.reason(request)

    assert result.candidates
    assert fallback.calls == []
    assert all(state.route == "mcp" for state in inbox.run_tasks(request.request_id))


def test_run_level_reasoner_registers_valid_empty_run(tmp_path) -> None:
    inbox, fallback, _multipass, reasoner = _build(tmp_path)
    now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    request = DreamReasoningRequest(
        request_id="empty-run",
        session_id="empty-session",
        focal_topics=[],
        session_start=now,
        session_end=now,
        evidence_by_topic={},
    )

    result = reasoner.reason(request)

    assert result.candidates == []
    assert fallback.calls == []
    assert inbox.run_ready("empty-run") is True
