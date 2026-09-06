# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cyberbrain.dreaming.reason_task_inbox import DreamReasonTaskInbox


def _request(task_id: str = "task-1") -> dict:
    return {
        "task_id": task_id,
        "request_id": "request-1",
        "topic": "routing",
        "kind": "current_state",
        "instruction": "Extract one supported current fact.",
        "evidence": [
            {
                "id": "evidence-1",
                "record_type": "knowledge",
                "content": "MCP is the preferred first Reasoner route.",
                "score": 1.0,
                "event_time": datetime.now(UTC).isoformat(),
                "metadata": {},
            }
        ],
    }


def test_publish_claim_submit_roundtrip(tmp_path) -> None:
    inbox = DreamReasonTaskInbox(tmp_path / "reason.sqlite")
    inbox.publish(_request(), wait_seconds=60)

    lease = inbox.claim_next(claimed_by="chatgpt:reasoner", lease_seconds=300)

    assert lease is not None
    assert lease.task["task_id"] == "task-1"
    result = inbox.submit(
        task_id="task-1",
        claim_token=lease.claim_token,
        claims=[
            {
                "claim": "MCP is the preferred first Reasoner route.",
                "evidence_ids": ["evidence-1"],
                "confidence": 0.95,
            }
        ],
    )
    assert result["status"] == "completed"
    assert result["route"] == "mcp"
    assert inbox.result("task-1")["claims"][0]["evidence_ids"] == ["evidence-1"]


def test_second_consumer_cannot_claim_active_lease(tmp_path) -> None:
    inbox = DreamReasonTaskInbox(tmp_path / "reason.sqlite")
    inbox.publish(_request(), wait_seconds=60)

    first = inbox.claim_next(claimed_by="chatgpt:first", lease_seconds=300)
    second = inbox.claim_next(claimed_by="chatgpt:second", lease_seconds=300)

    assert first is not None
    assert second is None


def test_submit_rejects_wrong_claim_token(tmp_path) -> None:
    inbox = DreamReasonTaskInbox(tmp_path / "reason.sqlite")
    inbox.publish(_request(), wait_seconds=60)
    lease = inbox.claim_next(claimed_by="chatgpt:reasoner", lease_seconds=300)
    assert lease is not None

    with pytest.raises(ValueError, match="claim token"):
        inbox.submit(
            task_id="task-1",
            claim_token="wrong",
            claims=[],
        )


def test_submit_rejects_unknown_evidence_id(tmp_path) -> None:
    inbox = DreamReasonTaskInbox(tmp_path / "reason.sqlite")
    inbox.publish(_request(), wait_seconds=60)
    lease = inbox.claim_next(claimed_by="chatgpt:reasoner", lease_seconds=300)
    assert lease is not None

    with pytest.raises(ValueError, match="unknown evidence"):
        inbox.submit(
            task_id="task-1",
            claim_token=lease.claim_token,
            claims=[
                {
                    "claim": "Unsupported",
                    "evidence_ids": ["fabricated"],
                    "confidence": 0.9,
                }
            ],
        )


def test_expired_deadline_is_not_claimable(tmp_path) -> None:
    inbox = DreamReasonTaskInbox(tmp_path / "reason.sqlite")
    inbox.publish(_request(), wait_seconds=0)

    assert inbox.claim_next(claimed_by="chatgpt:reasoner", lease_seconds=300) is None


def test_mark_fallback_does_not_overwrite_completed_result(tmp_path) -> None:
    inbox = DreamReasonTaskInbox(tmp_path / "reason.sqlite")
    inbox.publish(_request(), wait_seconds=60)
    lease = inbox.claim_next(claimed_by="chatgpt:reasoner", lease_seconds=300)
    assert lease is not None
    inbox.submit(
        task_id="task-1",
        claim_token=lease.claim_token,
        claims=[
            {
                "claim": "MCP is the preferred first Reasoner route.",
                "evidence_ids": ["evidence-1"],
                "confidence": 0.95,
            }
        ],
    )

    inbox.mark_fallback("task-1", route="9router")

    state = inbox.task_state("task-1")
    assert state is not None
    assert state.route == "mcp"
    assert inbox.result("task-1") is not None


def test_complete_fallback_never_overwrites_mcp_winner(tmp_path) -> None:
    inbox = DreamReasonTaskInbox(tmp_path / "reason.sqlite")
    inbox.publish(_request(), wait_seconds=60)
    lease = inbox.claim_next(claimed_by="chatgpt:reasoner", lease_seconds=300)
    assert lease is not None
    inbox.submit(
        task_id="task-1",
        claim_token=lease.claim_token,
        claims=[
            {
                "claim": "MCP winner",
                "evidence_ids": ["evidence-1"],
                "confidence": 0.99,
            }
        ],
    )

    winner = inbox.complete_fallback(
        task_id="task-1",
        result={
            "task_id": "task-1",
            "claims": [
                {
                    "claim": "Fallback loser",
                    "evidence_ids": ["evidence-1"],
                    "confidence": 0.5,
                }
            ],
        },
        route="fallback-router",
    )

    state = inbox.task_state("task-1")
    assert winner["claims"][0]["claim"] == "MCP winner"
    assert state is not None
    assert state.route == "mcp"


def test_register_run_is_atomic_when_task_registration_fails(tmp_path, monkeypatch) -> None:
    inbox = DreamReasonTaskInbox(tmp_path / "reason.sqlite")
    original = inbox._upsert_task
    calls = 0

    def fail_second(connection, **kwargs):  # noqa: ANN001, ANN003
        nonlocal calls
        calls += 1
        original(connection, **kwargs)
        if calls == 2:
            raise RuntimeError("injected registration failure")

    monkeypatch.setattr(inbox, "_upsert_task", fail_second)

    with pytest.raises(RuntimeError, match="injected registration failure"):
        inbox.register_run(
            request_id="request-1",
            request={"request_id": "request-1"},
            tasks=[_request("task-1"), _request("task-2")],
            wait_seconds=60,
        )

    with pytest.raises(KeyError):
        inbox.run_request("request-1")
    assert inbox.task_state("task-1") is None
    assert inbox.task_state("task-2") is None


def test_run_ready_fails_closed_on_partial_registration(tmp_path) -> None:
    inbox = DreamReasonTaskInbox(tmp_path / "reason.sqlite")
    inbox.register_run(
        request_id="request-1",
        request={"request_id": "request-1"},
        tasks=[_request("task-1"), _request("task-2")],
        wait_seconds=60,
    )

    with inbox._connect() as connection:
        connection.execute(
            "DELETE FROM dream_reason_tasks WHERE task_id='task-2'"
        )

    with pytest.raises(RuntimeError, match="task count mismatch"):
        inbox.run_ready("request-1")


def test_empty_registered_run_is_ready(tmp_path) -> None:
    inbox = DreamReasonTaskInbox(tmp_path / "reason.sqlite")
    inbox.register_run(
        request_id="request-empty",
        request={"request_id": "request-empty"},
        tasks=[],
        wait_seconds=60,
    )

    assert inbox.run_ready("request-empty") is True
