# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from cyberbrain.core.errors import ProviderUnavailableError
from cyberbrain.dreaming.adapters.mcp_transport import MCPStreamableHTTPInvoker
from cyberbrain.dreaming.audit import DreamRunAuditStore
from cyberbrain.dreaming.diagnostics import review_backlog
from cyberbrain.dreaming.heartbeat import heartbeat_status, write_heartbeat
from cyberbrain.dreaming.reason_task_inbox import DreamReasonTaskInbox
from tests.test_reason_task_inbox import _request


def test_review_diagnostics_distinguish_duplicates_from_new_evidence(tmp_path):
    path = tmp_path / "audit.sqlite"
    store = DreamRunAuditStore(path)
    now = datetime.now(UTC)
    with store._connect() as connection:
        for index, evidence in enumerate([["a"], ["a"], ["b"]]):
            connection.execute(
                "INSERT INTO dream_runs "
                "(id, session_id, request_id, status, input_evidence_ids_json, created_at) "
                "VALUES (?, ?, ?, 'evaluated', '[]', ?)",
                (f"run-{index}", "s", f"request-{index}", now.isoformat()),
            )
            connection.execute(
                "INSERT INTO dream_candidate_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"run-{index}", 0,
                    json.dumps({"content": "  Reuse   proven logic ", "entity_name": "reuse"}),
                    "review", 0.8, 0.2, 0.16, json.dumps(evidence),
                    json.dumps(["weak_evidence"]), (now - timedelta(days=index)).isoformat(),
                ),
            )
    report = review_backlog(path, limit=10, now=now)
    assert report["unresolved_total"] == 3
    assert report["duplicate_content_and_evidence"] == 1
    assert report["repeated_content"] == 2
    assert report["weak_evidence_count"] == 3
    assert report["reason_counts"] == {"weak_evidence": 3}
    assert report["review_queue"][0]["dream_run_id"] == "run-2"
    assert report["mutates_data"] is False
    assert len(store.pending_reviews()) == 3
    assert review_backlog(path, limit=1)["complete_scan"] is False


def test_diagnostics_do_not_create_missing_database(tmp_path):
    path = tmp_path / "absent.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        review_backlog(path)
    assert not path.exists()


def test_retirement_requires_finalized_ids_cutoff_and_preserves_replay_tombstone(tmp_path):
    inbox = DreamReasonTaskInbox(tmp_path / "reason.sqlite")
    past = datetime.now(UTC) - timedelta(days=60)
    inbox._now = lambda: past
    inbox.register_run(
        request_id="request-1", request={"id": "request-1"},
        tasks=[_request()], wait_seconds=0,
    )
    inbox._now = lambda: past + timedelta(days=60)
    cutoff = past + timedelta(days=30)
    preview = inbox.retire_finalized_runs(request_ids=["request-1"], before=cutoff)
    assert preview["dry_run"] and preview["task_count"] == 1
    assert inbox.task_state("task-1") is not None
    applied = inbox.retire_finalized_runs(
        request_ids=["request-1"], before=cutoff, dry_run=False,
    )
    assert applied["eligible_request_ids"] == ["request-1"]
    assert inbox.task_state("task-1") is None
    with pytest.raises(ValueError, match="retired"):
        inbox.register_run(
            request_id="request-1", request={}, tasks=[_request()], wait_seconds=0,
        )
    with pytest.raises(ValueError, match="retired"):
        inbox.publish(_request(), wait_seconds=0)


def test_retirement_blocks_active_leases_and_unknown_runs(tmp_path):
    inbox = DreamReasonTaskInbox(tmp_path / "reason.sqlite")
    now = datetime.now(UTC)
    past = now - timedelta(days=60)
    inbox._now = lambda: past
    inbox.register_run(
        request_id="request-1", request={}, tasks=[_request()], wait_seconds=60,
    )
    with inbox._connect() as connection:
        connection.execute(
            "UPDATE dream_reason_tasks SET status='claimed', lease_until=?",
            ((now + timedelta(seconds=300)).isoformat(),),
        )
    inbox._now = lambda: now
    result = inbox.retire_finalized_runs(
        request_ids=["request-1", "unknown"], before=now - timedelta(days=30), dry_run=False,
    )
    assert not result["eligible_request_ids"]
    assert inbox.task_state("task-1") is not None


@pytest.mark.parametrize("phase", ["waiting", "running", "error"])
def test_heartbeat_reports_freshness_and_execution_separately(tmp_path, phase):
    now = datetime.now(UTC)
    path = tmp_path / "heartbeat.json"
    write_heartbeat(
        path, phase=phase, next_run=now + timedelta(hours=1),
        error="StorageError" if phase == "error" else None, now=now,
    )
    status = heartbeat_status(path, now=now + timedelta(seconds=10))
    assert status["healthy"] is (phase != "error")
    assert status["has_completed_run"] is False
    assert not heartbeat_status(path, now=now + timedelta(hours=2))["healthy"]


def test_heartbeat_fails_closed_on_future_clock_bad_json_and_overdue_schedule(tmp_path):
    now = datetime.now(UTC)
    path = tmp_path / "heartbeat.json"
    assert not heartbeat_status(path)["healthy"]
    path.write_text("invalid", encoding="utf-8")
    assert not heartbeat_status(path)["healthy"]
    write_heartbeat(path, phase="waiting", next_run=now - timedelta(seconds=1), now=now)
    assert not heartbeat_status(path, now=now)["healthy"]
    write_heartbeat(path, phase="waiting", next_run=now + timedelta(hours=1), now=now)
    assert not heartbeat_status(path, now=now - timedelta(seconds=1))["healthy"]


def test_transport_classifies_nested_http_error_and_never_replays(monkeypatch):
    invoker = MCPStreamableHTTPInvoker(url="http://localhost/mcp")
    calls = []

    async def fail(tool, arguments):
        calls.append((tool, arguments))
        response = httpx.Response(404, request=httpx.Request("POST", "http://localhost/mcp"))
        error = httpx.HTTPStatusError(
            "internal dependency detail", request=response.request, response=response,
        )
        raise ExceptionGroup("dependency detail", [error])

    monkeypatch.setattr(invoker, "_call_tool", fail)
    with pytest.raises(ProviderUnavailableError, match="http_404") as raised:
        asyncio.run(invoker.invoke_async(tool="reason_task", arguments={"input": "example"}))
    assert len(calls) == 1
    assert "dependency detail" not in str(raised.value)
    assert invoker._failure_code(TimeoutError()) == "timeout"


def test_keyset_review_pagination_survives_ties_and_resolution(tmp_path):
    from cyberbrain.dreaming.operations import DreamOperations
    from cyberbrain.dreaming.queue import DreamQueue

    audit = DreamRunAuditStore(tmp_path / "audit.sqlite")
    created = datetime.now(UTC).isoformat()
    with audit._connect() as connection:
        for run_id in ["a", "b", "c"]:
            connection.execute(
                "INSERT INTO dream_runs "
                "(id, session_id, request_id, status, input_evidence_ids_json, created_at) "
                "VALUES (?, ?, ?, 'evaluated', '[]', ?)",
                (run_id, "s", "request-" + run_id, created),
            )
            connection.execute(
                "INSERT INTO dream_candidate_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, 0, json.dumps({"content": "example"}), "review",
                 0.8, 0.2, 0.16, "[]", "[]", created),
            )
    operations = DreamOperations(queue=DreamQueue(tmp_path / "queue.sqlite"), audit=audit)
    first = operations.pending_reviews(limit=1)
    with audit._connect() as connection:
        connection.execute(
            "INSERT INTO dream_candidate_reviews VALUES (?, ?, ?, ?, ?, ?)",
            ("a", 0, "rejected", "reviewer", None, created),
        )
    second = operations.pending_reviews(limit=1, cursor=first[-1]["review_cursor"])
    third = operations.pending_reviews(limit=1, cursor=second[-1]["review_cursor"])
    assert [row["dream_run_id"] for row in first + second + third] == ["a", "b", "c"]
    assert not operations.pending_reviews(limit=1, cursor=third[-1]["review_cursor"])
    with pytest.raises(ValueError, match="invalid review cursor"):
        operations.pending_reviews(cursor="broken")
