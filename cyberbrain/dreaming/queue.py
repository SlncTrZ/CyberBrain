# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


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

    def enqueue(self, session_id: str, topics: list[str]) -> DreamJob:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO dream_jobs (
                    session_id, topics_json, status, attempt_count, created_at, updated_at
                ) VALUES (?, ?, 'pending', 0, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    topics_json=excluded.topics_json,
                    updated_at=excluded.updated_at
                """,
                (session_id, json.dumps(topics, ensure_ascii=False), now, now),
            )
        return self.get_by_session(session_id)

    def get_by_session(self, session_id: str) -> DreamJob:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM dream_jobs WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return self._row_to_job(row)

    def pending(self, *, limit: int = 20) -> list[DreamJob]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM dream_jobs
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def claim_next(self) -> DreamJob | None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id FROM dream_jobs
                WHERE status='pending'
                ORDER BY created_at ASC
                LIMIT 1
                """
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
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id FROM dream_jobs
                WHERE status='failed' AND attempt_count < ?
                ORDER BY updated_at ASC
                LIMIT ?
                """,
                (max_attempts, limit),
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
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, attempt_count FROM dream_jobs WHERE status='processing'"
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

    def mark_processing(self, job_id: int) -> bool:
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

    def mark_processed(self, job_id: int) -> None:
        self._update_status(job_id, "processed")

    def mark_failed(self, job_id: int, error: str) -> None:
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
        )
