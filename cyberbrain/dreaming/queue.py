# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cyberbrain.tenancy.auth import (
    DeploymentMode,
    authority_for_authenticated_scope,
    current_authority,
)
from cyberbrain.tenancy.durable import (
    authority_snapshot,
    identity_key,
    restore_authority,
    snapshot_sql_filter,
    snapshot_visible,
)
from cyberbrain.tenancy.enforcement import TenancyOperation
from cyberbrain.tenancy.models import OperationClass
from cyberbrain.tenancy.runtime import enforce_operation


@dataclass(frozen=True)
class DreamJob:
    id: int
    session_id: str
    topics: list[str]
    status: str
    attempt_count: int
    created_at: str
    updated_at: str
    last_error: str | None
    authority_json: str | None = None


class DreamQueue:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS dream_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL UNIQUE,
                    topics_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_error TEXT
                )
                """
            )

            connection.execute("BEGIN IMMEDIATE")
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(dream_jobs)")}
            if "authority_json" not in columns:
                connection.execute("ALTER TABLE dream_jobs RENAME TO dream_jobs_legacy")
                connection.execute("""
                    CREATE TABLE dream_jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL, topics_json TEXT NOT NULL,
                        status TEXT NOT NULL, attempt_count INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_error TEXT,
                        authority_json TEXT, scope_key TEXT NOT NULL DEFAULT '{}',
                        UNIQUE(session_id, scope_key)
                    )
                """)
                connection.execute("""
                    INSERT INTO dream_jobs (
                        id, session_id, topics_json, status, attempt_count,
                        created_at, updated_at, last_error
                    ) SELECT id, session_id, topics_json, status, attempt_count,
                             created_at, updated_at, last_error FROM dream_jobs_legacy
                """)
                connection.execute("DROP TABLE dream_jobs_legacy")
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(dream_jobs)")}
            if "available_at" not in columns:
                connection.execute(
                    "ALTER TABLE dream_jobs ADD COLUMN available_at REAL NOT NULL DEFAULT 0"
                )

    def enqueue(
        self, session_id: str, topics: list[str], *, authority_json: str | None = None,
    ) -> DreamJob:
        plan = enforce_operation(TenancyOperation.MEMORY_WRITE, {"session_id": session_id})
        caller = current_authority()
        if authority_json is None and caller is not None:
            # The server owns consolidation after an authorized write/enqueue.
            # Delegate internal operations inside the same concrete scope only.
            delegated = authority_for_authenticated_scope(
                caller.deployment_mode, scope=plan.effective_scope,
                operations=frozenset(OperationClass),
            )
            snapshot = authority_snapshot(delegated)
        else:
            snapshot = authority_json or authority_snapshot()
        restore_authority(snapshot)
        key = identity_key(snapshot)
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO dream_jobs (
                    session_id, topics_json, status, attempt_count, created_at, updated_at,
                    authority_json, scope_key
                ) VALUES (?, ?, 'pending', 0, ?, ?, ?, ?)
                ON CONFLICT(session_id, scope_key) DO UPDATE SET
                    topics_json=excluded.topics_json,
                    updated_at=excluded.updated_at
                """,
                (session_id, json.dumps(topics, ensure_ascii=False), now, now, snapshot, key),
            )
        return self.get_by_session(session_id, authority_json=snapshot)

    def get_by_session(
        self, session_id: str, *, authority_json: str | None = None,
    ) -> DreamJob:
        snapshot = authority_json
        with self._connect() as connection:
            if snapshot is None:
                clause, parameters = snapshot_sql_filter("authority_json")
                rows = connection.execute(
                    "SELECT * FROM dream_jobs WHERE session_id = ?" + clause,
                    (session_id, *parameters),
                ).fetchall()
                if len(rows) != 1:
                    raise KeyError(session_id)
                row = rows[0]
            else:
                row = connection.execute(
                    "SELECT * FROM dream_jobs WHERE session_id = ? AND scope_key = ?",
                    (session_id, identity_key(snapshot)),
                ).fetchone()
        if row is None or not snapshot_visible(row["authority_json"]):
            raise KeyError(session_id)
        return self._row_to_job(row)

    def pending(self, *, limit: int = 20) -> list[DreamJob]:
        scope_clause, parameters = snapshot_sql_filter("authority_json")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM dream_jobs
                WHERE status = 'pending' AND available_at <= ?
                """ + scope_clause + """
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (time.time(), *parameters, limit),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def claim_next(
        self, *, deployment_mode: DeploymentMode = DeploymentMode.SINGLE_OWNER,
    ) -> DreamJob | None:
        scope_clause, parameters = snapshot_sql_filter("authority_json")
        if deployment_mode is not DeploymentMode.SINGLE_OWNER:
            scope_clause += " AND json_extract(authority_json, '$.mode') = ?"
            parameters.append(deployment_mode.value)
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id FROM dream_jobs
                WHERE status='pending' AND available_at <= ?
                """ + scope_clause + """
                ORDER BY created_at ASC
                LIMIT 1
                """, (time.time(), *parameters),
            ).fetchone()
            if row is None:
                return None
            job_id = int(row["id"])
            updated = connection.execute(
                """
                UPDATE dream_jobs
                SET status='processing', attempt_count=attempt_count+1,
                    updated_at=?, last_error=NULL
                WHERE id=? AND status='pending'
                """,
                (now, job_id),
            )
            if updated.rowcount != 1:
                return None
            claimed = connection.execute(
                "SELECT * FROM dream_jobs WHERE id=?",
                (job_id,),
            ).fetchone()
        return self._row_to_job(claimed) if claimed is not None else None

    def retry_failed(self, *, max_attempts: int, limit: int = 20) -> int:
        scope_clause, parameters = snapshot_sql_filter("authority_json")
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id FROM dream_jobs
                WHERE status='failed' AND attempt_count < ?
                """ + scope_clause + """
                ORDER BY updated_at ASC
                LIMIT ?
                """,
                (max_attempts, *parameters, limit),
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            for job_id in ids:
                connection.execute(
                    """
                    UPDATE dream_jobs
                    SET status='pending', updated_at=?
                    WHERE id=?
                    """,
                    (now, job_id),
                )
        return len(ids)

    def recover_processing(self, *, max_attempts: int) -> int:
        scope_clause, parameters = snapshot_sql_filter("authority_json")
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, attempt_count FROM dream_jobs WHERE status='processing'" + scope_clause,
                parameters,
            ).fetchall()
            for row in rows:
                status = "pending" if int(row["attempt_count"]) < max_attempts else "failed"
                connection.execute(
                    """
                    UPDATE dream_jobs
                    SET status=?, last_error='worker_restarted', updated_at=?
                    WHERE id=?
                    """,
                    (status, now, int(row["id"])),
                )
        return len(rows)

    def assert_visible(self, job_id: int) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT authority_json FROM dream_jobs WHERE id=?", (job_id,),
            ).fetchone()
        if row is None or not snapshot_visible(row["authority_json"]):
            raise KeyError(job_id)

    def mark_processing(self, job_id: int) -> bool:
        self.assert_visible(job_id)
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            updated = connection.execute(
                """
                UPDATE dream_jobs
                SET status='processing', attempt_count=attempt_count+1,
                    updated_at=?, last_error=NULL
                WHERE id=? AND status='pending'
                """,
                (now, job_id),
            )
        return updated.rowcount == 1

    def defer(self, job_id: int, *, retry_after: int) -> None:
        self.assert_visible(job_id)
        with self._connect() as connection:
            connection.execute("""
                UPDATE dream_jobs SET status='pending', available_at=?,
                    attempt_count=MAX(attempt_count-1, 0), last_error='quota_exceeded',
                    updated_at=? WHERE id=? AND status='processing'
            """, (time.time() + retry_after, datetime.now(UTC).isoformat(), job_id))

    def mark_processed(self, job_id: int) -> None:
        self._update_status(job_id, "processed")

    def mark_failed(self, job_id: int, error: str) -> None:
        self.assert_visible(job_id)
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE dream_jobs
                SET status='failed', last_error=?, updated_at=?
                WHERE id=?
                """,
                (error[:1000], now, job_id),
            )

    def retry(self, job_id: int) -> None:
        self._update_status(job_id, "pending")

    def _update_status(self, job_id: int, status: str, *, increment_attempt: bool = False) -> None:
        self.assert_visible(job_id)
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            if increment_attempt:
                connection.execute(
                    """
                    UPDATE dream_jobs
                    SET status=?, attempt_count=attempt_count+1, updated_at=?, last_error=NULL
                    WHERE id=?
                    """,
                    (status, now, job_id),
                )
            else:
                connection.execute(
                    """
                    UPDATE dream_jobs
                    SET status=?, updated_at=?
                    WHERE id=?
                    """,
                    (status, now, job_id),
                )

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> DreamJob:
        return DreamJob(
            id=int(row["id"]),
            session_id=str(row["session_id"]),
            topics=list(json.loads(row["topics_json"])),
            status=str(row["status"]),
            attempt_count=int(row["attempt_count"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            last_error=row["last_error"],
            authority_json=row["authority_json"],
        )
