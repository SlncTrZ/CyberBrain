# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from cyberbrain.dreaming.gate import DreamGateResult
from cyberbrain.dreaming.reasoner import DreamReasoningRequest, DreamReasoningResult


@dataclass(frozen=True)
class DreamRun:
    id: str
    session_id: str
    request_id: str
    status: str
    input_evidence_ids: list[str]
    candidate_count: int
    created_at: str
    completed_at: str | None


class DreamRunAuditStore:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS dream_runs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    request_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    input_evidence_ids_json TEXT NOT NULL,
                    request_json TEXT,
                    candidate_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS dream_candidate_decisions (
                    dream_run_id TEXT NOT NULL,
                    candidate_index INTEGER NOT NULL,
                    candidate_json TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reasoner_confidence REAL NOT NULL,
                    evidence_strength REAL NOT NULL,
                    promotion_confidence REAL NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (dream_run_id, candidate_index),
                    FOREIGN KEY (dream_run_id) REFERENCES dream_runs(id)
                );

                CREATE TABLE IF NOT EXISTS dream_candidate_writes (
                    dream_run_id TEXT NOT NULL,
                    candidate_index INTEGER NOT NULL,
                    write_status TEXT NOT NULL,
                    write_reason TEXT NOT NULL,
                    evolution_outcome TEXT,
                    knowledge_id TEXT,
                    previous_knowledge_id TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (dream_run_id, candidate_index),
                    FOREIGN KEY (dream_run_id) REFERENCES dream_runs(id)
                );

                CREATE TABLE IF NOT EXISTS dream_candidate_reviews (
                    dream_run_id TEXT NOT NULL,
                    candidate_index INTEGER NOT NULL,
                    resolution TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (dream_run_id, candidate_index),
                    FOREIGN KEY (dream_run_id) REFERENCES dream_runs(id)
                );
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(dream_runs)").fetchall()
            }
            if "request_json" not in columns:
                connection.execute("ALTER TABLE dream_runs ADD COLUMN request_json TEXT")

    def start(self, *, dream_run_id: str, request: DreamReasoningRequest) -> DreamRun:
        evidence_ids = sorted(
            {
                item.id
                for items in request.evidence_by_topic.values()
                for item in items
            }
        )
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO dream_runs (
                    id, session_id, request_id, status,
                    input_evidence_ids_json, request_json, candidate_count,
                    created_at, completed_at
                ) VALUES (?, ?, ?, 'processing', ?, ?, 0, ?, NULL)
                ON CONFLICT(request_id) DO NOTHING
                """,
                (
                    dream_run_id,
                    request.session_id,
                    request.request_id,
                    json.dumps(evidence_ids, ensure_ascii=False),
                    json.dumps(asdict(request), ensure_ascii=False, default=str),
                    now,
                ),
            )
        return self.get_by_request(request.request_id)

    def complete(
        self,
        *,
        dream_run_id: str,
        result: DreamReasoningResult,
        gate: DreamGateResult,
    ) -> DreamRun:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            for decision in gate.candidates:
                candidate = result.candidates[decision.candidate_index]
                connection.execute(
                    """
                    INSERT OR REPLACE INTO dream_candidate_decisions (
                        dream_run_id, candidate_index, candidate_json, decision,
                        reasoner_confidence, evidence_strength, promotion_confidence,
                        evidence_ids_json, reasons_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        dream_run_id,
                        decision.candidate_index,
                        json.dumps(asdict(candidate), ensure_ascii=False),
                        decision.decision.value,
                        decision.reasoner_confidence,
                        decision.evidence_strength,
                        decision.promotion_confidence,
                        json.dumps(decision.evidence_ids, ensure_ascii=False),
                        json.dumps(decision.reasons, ensure_ascii=False),
                        now,
                    ),
                )
            connection.execute(
                """
                UPDATE dream_runs
                SET status='evaluated', candidate_count=?, completed_at=?
                WHERE id=?
                """,
                (len(result.candidates), now, dream_run_id),
            )
        return self.get(dream_run_id)

    def mark_failed(self, dream_run_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE dream_runs
                SET status='failed', completed_at=?
                WHERE id=?
                """,
                (now, dream_run_id),
            )

    def get(self, dream_run_id: str) -> DreamRun:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM dream_runs WHERE id=?",
                (dream_run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(dream_run_id)
        return self._row_to_run(row)

    def request_snapshot(self, dream_run_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT request_json FROM dream_runs WHERE id=?",
                (dream_run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(dream_run_id)
        raw = row["request_json"]
        if not raw:
            raise ValueError("dream run does not contain a request snapshot")
        value = json.loads(str(raw))
        if not isinstance(value, dict):
            raise ValueError("dream request snapshot must be an object")
        return value

    def get_by_request(self, request_id: str) -> DreamRun:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM dream_runs WHERE request_id=?",
                (request_id,),
            ).fetchone()
        if row is None:
            raise KeyError(request_id)
        return self._row_to_run(row)

    def decisions(self, dream_run_id: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM dream_candidate_decisions
                WHERE dream_run_id=?
                ORDER BY candidate_index ASC
                """,
                (dream_run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def decision(self, dream_run_id: str, candidate_index: int) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM dream_candidate_decisions
                WHERE dream_run_id=? AND candidate_index=?
                """,
                (dream_run_id, candidate_index),
            ).fetchone()
        if row is None:
            raise KeyError((dream_run_id, candidate_index))
        return dict(row)

    def record_write(
        self,
        *,
        dream_run_id: str,
        candidate_index: int,
        write_status: str,
        write_reason: str,
        evolution_outcome: str | None = None,
        knowledge_id: str | None = None,
        previous_knowledge_id: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO dream_candidate_writes (
                    dream_run_id, candidate_index, write_status, write_reason,
                    evolution_outcome, knowledge_id, previous_knowledge_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dream_run_id,
                    candidate_index,
                    write_status,
                    write_reason,
                    evolution_outcome,
                    knowledge_id,
                    previous_knowledge_id,
                    now,
                ),
            )

    def write(self, dream_run_id: str, candidate_index: int) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM dream_candidate_writes
                WHERE dream_run_id=? AND candidate_index=?
                """,
                (dream_run_id, candidate_index),
            ).fetchone()
        return dict(row) if row is not None else None

    def writes(self, dream_run_id: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM dream_candidate_writes
                WHERE dream_run_id=?
                ORDER BY candidate_index ASC
                """,
                (dream_run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def pending_reviews(self, *, limit: int = 100) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT d.*
                FROM dream_candidate_decisions AS d
                LEFT JOIN dream_candidate_reviews AS r
                  ON r.dream_run_id=d.dream_run_id
                 AND r.candidate_index=d.candidate_index
                WHERE d.decision='review' AND r.dream_run_id IS NULL
                ORDER BY d.created_at ASC, d.candidate_index ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def resolve_review(
        self,
        *,
        dream_run_id: str,
        candidate_index: int,
        resolution: str,
        reviewer: str,
        reason: str | None = None,
    ) -> None:
        if resolution not in {"approved", "rejected"}:
            raise ValueError("review resolution must be approved or rejected")
        reviewer_value = reviewer.strip()
        if not reviewer_value:
            raise ValueError("reviewer must not be empty")

        with self._connect() as connection:
            decision = connection.execute(
                """
                SELECT decision FROM dream_candidate_decisions
                WHERE dream_run_id=? AND candidate_index=?
                """,
                (dream_run_id, candidate_index),
            ).fetchone()
            if decision is None:
                raise KeyError((dream_run_id, candidate_index))
            if decision["decision"] != "review":
                raise ValueError("only review candidates can be manually resolved")
            existing = connection.execute(
                """
                SELECT resolution FROM dream_candidate_reviews
                WHERE dream_run_id=? AND candidate_index=?
                """,
                (dream_run_id, candidate_index),
            ).fetchone()
            if existing is not None:
                raise ValueError("review candidate is already resolved")
            connection.execute(
                """
                INSERT INTO dream_candidate_reviews (
                    dream_run_id, candidate_index, resolution, reviewer, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    dream_run_id,
                    candidate_index,
                    resolution,
                    reviewer_value,
                    reason,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def review_resolution(self, dream_run_id: str, candidate_index: int) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM dream_candidate_reviews
                WHERE dream_run_id=? AND candidate_index=?
                """,
                (dream_run_id, candidate_index),
            ).fetchone()
        return dict(row) if row is not None else None

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> DreamRun:
        return DreamRun(
            id=str(row["id"]),
            session_id=str(row["session_id"]),
            request_id=str(row["request_id"]),
            status=str(row["status"]),
            input_evidence_ids=list(json.loads(row["input_evidence_ids_json"])),
            candidate_count=int(row["candidate_count"]),
            created_at=str(row["created_at"]),
            completed_at=row["completed_at"],
        )
