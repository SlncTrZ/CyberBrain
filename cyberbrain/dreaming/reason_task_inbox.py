# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from cyberbrain.reasoner_provider.contracts import (
    ReasonTaskRequest,
    ReasonTaskResult,
    validate_task_result,
)


@dataclass(frozen=True)
class ReasonTaskLease:
    task: dict
    claim_token: str
    claimed_by: str
    lease_until: str
    deadline_at: str


@dataclass(frozen=True)
class ReasonTaskState:
    task: dict
    status: str
    route: str | None
    result: dict | None
    deadline_at: str


class DreamReasonTaskInbox:
    """Durable MCP handoff inbox and run snapshot store for Dream micro-reasoning."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        Path(self._path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS dream_reason_tasks (
                    task_id TEXT PRIMARY KEY,
                    request_id TEXT,
                    request_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    claim_token TEXT,
                    claimed_by TEXT,
                    lease_until TEXT,
                    deadline_at TEXT NOT NULL,
                    result_json TEXT,
                    route TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            task_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(dream_reason_tasks)")
            }
            if "request_id" not in task_columns:
                connection.execute(
                    "ALTER TABLE dream_reason_tasks ADD COLUMN request_id TEXT"
                )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dream_reason_tasks_request
                ON dream_reason_tasks(request_id, status, created_at)
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS dream_reason_runs (
                    request_id TEXT PRIMARY KEY,
                    request_json TEXT NOT NULL,
                    expected_task_count INTEGER NOT NULL DEFAULT 0,
                    deadline_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            run_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(dream_reason_runs)")
            }
            if "expected_task_count" not in run_columns:
                connection.execute(
                    """
                    ALTER TABLE dream_reason_runs
                    ADD COLUMN expected_task_count INTEGER NOT NULL DEFAULT 0
                    """
                )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(UTC).isoformat()

    def register_run(
        self,
        *,
        request_id: str,
        request: dict,
        tasks: list[dict],
        wait_seconds: float,
    ) -> None:
        """Atomically register one Dream run and its complete initial task set."""

        value = request_id.strip()
        if not value:
            raise ValueError("request_id must not be empty")
        if wait_seconds < 0:
            raise ValueError("wait_seconds must be >= 0")

        task_models = [ReasonTaskRequest.model_validate(task) for task in tasks]
        task_ids = [task.task_id for task in task_models]
        duplicates = sorted(
            task_id for task_id in set(task_ids) if task_ids.count(task_id) > 1
        )
        if duplicates:
            raise ValueError(f"duplicate reason task IDs in run: {duplicates}")
        wrong_run = sorted(
            task.task_id for task in task_models if task.request_id != value
        )
        if wrong_run:
            raise ValueError(
                f"reason tasks do not belong to request {value!r}: {wrong_run}"
            )

        now = self._now()
        deadline = now + timedelta(seconds=float(wait_seconds))
        now_iso = self._iso(now)
        deadline_iso = self._iso(deadline)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO dream_reason_runs (
                    request_id, request_json, expected_task_count,
                    deadline_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    request_json=excluded.request_json,
                    expected_task_count=excluded.expected_task_count,
                    deadline_at=excluded.deadline_at,
                    updated_at=excluded.updated_at
                """,
                (
                    value,
                    json.dumps(request, ensure_ascii=False),
                    len(task_models),
                    deadline_iso,
                    now_iso,
                    now_iso,
                ),
            )
            for task_model in task_models:
                self._upsert_task(
                    connection,
                    request_model=task_model,
                    request_id=value,
                    deadline_at=deadline,
                    now=now,
                )

    def publish(
        self,
        request: dict,
        *,
        wait_seconds: float,
        request_id: str | None = None,
        deadline_at: datetime | None = None,
    ) -> None:
        """Publish one standalone task; retained for compatibility and focused tests."""

        if wait_seconds < 0:
            raise ValueError("wait_seconds must be >= 0")
        request_model = ReasonTaskRequest.model_validate(request)
        now = self._now()
        deadline = deadline_at or (now + timedelta(seconds=float(wait_seconds)))
        run_id = (request_id or request_model.request_id).strip()
        if not run_id:
            raise ValueError("request_id must not be empty")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._upsert_task(
                connection,
                request_model=request_model,
                request_id=run_id,
                deadline_at=deadline,
                now=now,
            )

    def _upsert_task(
        self,
        connection: sqlite3.Connection,
        *,
        request_model: ReasonTaskRequest,
        request_id: str,
        deadline_at: datetime,
        now: datetime,
    ) -> None:
        connection.execute(
            """
            INSERT INTO dream_reason_tasks (
                task_id, request_id, request_json, status,
                deadline_at, created_at, updated_at
            ) VALUES (?, ?, ?, 'pending', ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                request_id=excluded.request_id,
                request_json=excluded.request_json,
                status=CASE
                    WHEN dream_reason_tasks.status='completed' THEN 'completed'
                    ELSE 'pending'
                END,
                deadline_at=excluded.deadline_at,
                claim_token=CASE
                    WHEN dream_reason_tasks.status='completed'
                    THEN dream_reason_tasks.claim_token
                    ELSE NULL
                END,
                claimed_by=CASE
                    WHEN dream_reason_tasks.status='completed'
                    THEN dream_reason_tasks.claimed_by
                    ELSE NULL
                END,
                lease_until=CASE
                    WHEN dream_reason_tasks.status='completed'
                    THEN dream_reason_tasks.lease_until
                    ELSE NULL
                END,
                result_json=CASE
                    WHEN dream_reason_tasks.status='completed'
                    THEN dream_reason_tasks.result_json
                    ELSE NULL
                END,
                route=CASE
                    WHEN dream_reason_tasks.status='completed'
                    THEN dream_reason_tasks.route
                    ELSE NULL
                END,
                updated_at=excluded.updated_at
            """,
            (
                request_model.task_id,
                request_id,
                request_model.model_dump_json(),
                self._iso(deadline_at),
                self._iso(now),
                self._iso(now),
            ),
        )

    def claim_next(
        self,
        *,
        claimed_by: str,
        lease_seconds: int = 300,
    ) -> ReasonTaskLease | None:
        consumer = claimed_by.strip()
        if not consumer:
            raise ValueError("claimed_by must not be empty")
        if lease_seconds < 30 or lease_seconds > 3600:
            raise ValueError("lease_seconds must be between 30 and 3600")

        now = self._now()
        lease_until = now + timedelta(seconds=lease_seconds)
        now_iso = self._iso(now)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT *
                FROM dream_reason_tasks
                WHERE deadline_at > ?
                  AND (
                    status='pending'
                    OR (
                      status='claimed'
                      AND (lease_until IS NULL OR lease_until <= ?)
                    )
                  )
                ORDER BY created_at ASC, task_id ASC
                LIMIT 1
                """,
                (now_iso, now_iso),
            ).fetchone()
            if row is None:
                return None
            token = uuid4().hex
            updated = connection.execute(
                """
                UPDATE dream_reason_tasks
                SET status='claimed',
                    claim_token=?,
                    claimed_by=?,
                    lease_until=?,
                    updated_at=?
                WHERE task_id=?
                  AND deadline_at > ?
                  AND (
                    status='pending'
                    OR (
                      status='claimed'
                      AND (lease_until IS NULL OR lease_until <= ?)
                    )
                  )
                """,
                (
                    token,
                    consumer,
                    self._iso(lease_until),
                    now_iso,
                    str(row["task_id"]),
                    now_iso,
                    now_iso,
                ),
            )
            if updated.rowcount != 1:
                return None
            claimed = connection.execute(
                "SELECT * FROM dream_reason_tasks WHERE task_id=?",
                (str(row["task_id"]),),
            ).fetchone()

        if claimed is None:
            return None
        return ReasonTaskLease(
            task=json.loads(str(claimed["request_json"])),
            claim_token=str(claimed["claim_token"]),
            claimed_by=str(claimed["claimed_by"]),
            lease_until=str(claimed["lease_until"]),
            deadline_at=str(claimed["deadline_at"]),
        )

    def submit(
        self,
        *,
        task_id: str,
        claim_token: str,
        claims: list[dict],
    ) -> dict:
        task_value = task_id.strip()
        token_value = claim_token.strip()
        if not task_value or not token_value:
            raise ValueError("task_id and claim_token must not be empty")

        now = self._now()
        now_iso = self._iso(now)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM dream_reason_tasks WHERE task_id=?",
                (task_value,),
            ).fetchone()
            if row is None:
                raise KeyError(task_value)
            if str(row["status"]) != "claimed":
                raise ValueError("reason task is not currently claimed")
            if str(row["claim_token"] or "") != token_value:
                raise ValueError("reason task claim token does not match")

            lease_until = datetime.fromisoformat(
                str(row["lease_until"]).replace("Z", "+00:00")
            )
            deadline_at = datetime.fromisoformat(
                str(row["deadline_at"]).replace("Z", "+00:00")
            )
            if lease_until <= now:
                raise ValueError("reason task lease has expired")
            if deadline_at <= now:
                raise ValueError("reason task deadline has expired")

            request_model = ReasonTaskRequest.model_validate_json(
                str(row["request_json"])
            )
            result_model = ReasonTaskResult.model_validate(
                {"task_id": task_value, "claims": claims}
            )
            validate_task_result(request_model, result_model)

            updated = connection.execute(
                """
                UPDATE dream_reason_tasks
                SET status='completed',
                    result_json=?,
                    route='mcp',
                    updated_at=?
                WHERE task_id=?
                  AND status='claimed'
                  AND claim_token=?
                  AND deadline_at > ?
                """,
                (
                    result_model.model_dump_json(),
                    now_iso,
                    task_value,
                    token_value,
                    now_iso,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError("reason task changed before MCP submission completed")

        return {
            "task_id": task_value,
            "status": "completed",
            "route": "mcp",
            "claims": result_model.model_dump(mode="json")["claims"],
        }

    def complete_fallback(
        self,
        *,
        task_id: str,
        result: dict,
        route: str,
    ) -> dict:
        """Complete an unfinished task without overwriting an MCP winner."""

        task_value = task_id.strip()
        route_value = route.strip()
        if not task_value:
            raise ValueError("task_id must not be empty")
        if not route_value or route_value == "mcp":
            raise ValueError("fallback route must identify a non-MCP route")

        now_iso = self._iso(self._now())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM dream_reason_tasks WHERE task_id=?",
                (task_value,),
            ).fetchone()
            if row is None:
                raise KeyError(task_value)
            if str(row["status"]) == "completed":
                return json.loads(str(row["result_json"]))

            request_model = ReasonTaskRequest.model_validate_json(
                str(row["request_json"])
            )
            result_model = ReasonTaskResult.model_validate(result)
            validate_task_result(request_model, result_model)

            updated = connection.execute(
                """
                UPDATE dream_reason_tasks
                SET status='completed',
                    result_json=?,
                    route=?,
                    updated_at=?
                WHERE task_id=? AND status!='completed'
                """,
                (
                    result_model.model_dump_json(),
                    route_value,
                    now_iso,
                    task_value,
                ),
            )
            if updated.rowcount == 1:
                return result_model.model_dump(mode="json")

            winner = connection.execute(
                """
                SELECT status, result_json
                FROM dream_reason_tasks
                WHERE task_id=?
                """,
                (task_value,),
            ).fetchone()
            if (
                winner is None
                or str(winner["status"]) != "completed"
                or winner["result_json"] is None
            ):
                raise RuntimeError("reason task fallback lost race without a completed winner")
            return json.loads(str(winner["result_json"]))

    def result(self, task_id: str) -> dict | None:
        state = self.task_state(task_id)
        return state.result if state is not None and state.status == "completed" else None

    def task_state(self, task_id: str) -> ReasonTaskState | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM dream_reason_tasks WHERE task_id=?",
                (task_id.strip(),),
            ).fetchone()
        if row is None:
            return None
        return self._state_from_row(row)

    def run_request(self, request_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT request_json FROM dream_reason_runs WHERE request_id=?",
                (request_id.strip(),),
            ).fetchone()
        if row is None:
            raise KeyError(request_id)
        return json.loads(str(row["request_json"]))

    def run_tasks(self, request_id: str) -> list[ReasonTaskState]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM dream_reason_tasks
                WHERE request_id=?
                ORDER BY created_at ASC, task_id ASC
                """,
                (request_id.strip(),),
            ).fetchall()
        return [self._state_from_row(row) for row in rows]

    def run_ready(self, request_id: str) -> bool:
        """Return true when all tasks completed or the common MCP deadline expired."""

        value = request_id.strip()
        with self._connect() as connection:
            run = connection.execute(
                """
                SELECT expected_task_count, deadline_at
                FROM dream_reason_runs
                WHERE request_id=?
                """,
                (value,),
            ).fetchone()
            if run is None:
                raise KeyError(value)
            rows = connection.execute(
                """
                SELECT status
                FROM dream_reason_tasks
                WHERE request_id=?
                """,
                (value,),
            ).fetchall()

        expected = int(run["expected_task_count"])
        if len(rows) != expected:
            raise RuntimeError(
                "reason run task count mismatch: "
                f"expected={expected}, actual={len(rows)}"
            )
        if expected == 0:
            return True
        if all(str(row["status"]) == "completed" for row in rows):
            return True

        deadline = datetime.fromisoformat(
            str(run["deadline_at"]).replace("Z", "+00:00")
        )
        return deadline <= self._now()

    def mark_fallback(self, task_id: str, *, route: str) -> None:
        """Legacy state marker retained for compatibility with the v0.1.1 router."""

        now_iso = self._iso(self._now())
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE dream_reason_tasks
                SET status='fallback',
                    route=?,
                    updated_at=?
                WHERE task_id=? AND status!='completed'
                """,
                (route, now_iso, task_id.strip()),
            )

    @staticmethod
    def _state_from_row(row: sqlite3.Row) -> ReasonTaskState:
        return ReasonTaskState(
            task=json.loads(str(row["request_json"])),
            status=str(row["status"]),
            route=(str(row["route"]) if row["route"] is not None else None),
            result=(
                json.loads(str(row["result_json"]))
                if row["result_json"] is not None
                else None
            ),
            deadline_at=str(row["deadline_at"]),
        )
