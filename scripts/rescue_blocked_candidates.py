# SPDX-License-Identifier: MPL-2.0
"""Rescue dream candidates blocked by missing/ambiguous domain metadata.
Updated: 2026-10-24 11:30
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cyberbrain.core.runtime import build_runtime
from cyberbrain.core.settings import Settings
from cyberbrain.dreaming.gate import CandidateGateResult, PromotionDecision
from cyberbrain.dreaming.queue import DreamQueue
from cyberbrain.dreaming.reasoner import (
    DreamCandidate,
    DreamReasoningRequest,
    EvidenceItem,
)
from cyberbrain.dreaming.writeback import DreamKnowledgeWriter, DreamWriteStatus
from cyberbrain.tenancy.durable import bind_job_authority, restore_authority


def parse_request_snapshot(snapshot_raw: str | dict[str, Any]) -> DreamReasoningRequest:
    snapshot = json.loads(snapshot_raw) if isinstance(snapshot_raw, str) else snapshot_raw
    evidence_by_topic: dict[str, list[EvidenceItem]] = {}
    for topic, items in dict(snapshot.get("evidence_by_topic") or {}).items():
        evidence_by_topic[str(topic)] = [
            EvidenceItem(
                id=str(item["id"]),
                record_type=str(item["record_type"]),
                content=str(item["content"]),
                score=(float(item["score"]) if item.get("score") is not None else None),
                event_time=(
                    datetime.fromisoformat(str(item["event_time"]).replace("Z", "+00:00"))
                    if item.get("event_time")
                    else None
                ),
                metadata=dict(item.get("metadata") or {}),
            )
            for item in items
        ]
    return DreamReasoningRequest(
        request_id=str(snapshot["request_id"]),
        session_id=str(snapshot["session_id"]),
        focal_topics=[str(topic) for topic in snapshot.get("focal_topics") or []],
        session_start=datetime.fromisoformat(
            str(snapshot["session_start"]).replace("Z", "+00:00")
        ),
        session_end=datetime.fromisoformat(
            str(snapshot["session_end"]).replace("Z", "+00:00")
        ),
        evidence_by_topic=evidence_by_topic,
        instructions_version=str(snapshot.get("instructions_version") or "1"),
    )


def rescue_blocked_candidates(
    *,
    audit_db_path: Path,
    queue_db_path: Path | None = None,
    default_domain: str = "engineering",
    dry_run: bool = False,
    requeue_failed: bool = False,
    qdrant_url: str | None = None,
    embedding_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    if not audit_db_path.exists():
        raise FileNotFoundError(f"Audit database not found: {audit_db_path}")

    conn = sqlite3.connect(str(audit_db_path))
    conn.row_factory = sqlite3.Row

    query = """
    SELECT
        w.dream_run_id,
        w.candidate_index,
        w.write_status,
        w.write_reason,
        d.candidate_json,
        d.evidence_ids_json,
        d.reasoner_confidence,
        d.evidence_strength,
        d.promotion_confidence,
        d.reasons_json,
        r.resolution,
        r.reviewer,
        run.request_json,
        run.authority_json
    FROM dream_candidate_writes w
    JOIN dream_candidate_decisions d
        ON d.dream_run_id = w.dream_run_id AND d.candidate_index = w.candidate_index
    JOIN dream_candidate_reviews r
        ON r.dream_run_id = w.dream_run_id AND r.candidate_index = w.candidate_index
    JOIN dream_runs run
        ON run.id = w.dream_run_id
    WHERE w.write_status = 'blocked_metadata'
      AND r.resolution = 'approved'
    ORDER BY w.created_at ASC
    """

    rows = conn.execute(query).fetchall()
    print(f"Found {len(rows)} approved candidates blocked by metadata.")

    if not rows and not requeue_failed:
        conn.close()
        return {"rescued": 0, "errors": 0}

    settings = Settings()
    if default_domain:
        settings.dream_default_domain = default_domain
    if qdrant_url:
        settings.qdrant_url = qdrant_url
    if embedding_url:
        settings.embedding_url = embedding_url
    if api_key:
        settings.qdrant_api_key = api_key
    services = build_runtime(settings)
    writer = DreamKnowledgeWriter(
        services.knowledge_evolution,
        default_domain=default_domain,
    )

    rescued = 0
    errors = 0
    domain_counts: dict[str, int] = {}

    for row in rows:
        dream_run_id = str(row["dream_run_id"])
        candidate_index = int(row["candidate_index"])
        try:
            candidate_payload = json.loads(str(row["candidate_json"]))
            evidence_ids = list(json.loads(str(row["evidence_ids_json"])))
            reasons = list(json.loads(str(row["reasons_json"])))
            candidate = DreamCandidate(**candidate_payload)
            request = parse_request_snapshot(row["request_json"])
            authority_json = row["authority_json"]
            if authority_json:
                restore_authority(authority_json)
            else:
                bind_job_authority(None)

            decision = CandidateGateResult(
                candidate_index=candidate_index,
                decision=PromotionDecision.PROMOTE,
                reasoner_confidence=float(row["reasoner_confidence"]),
                evidence_strength=float(row["evidence_strength"]),
                promotion_confidence=float(row["promotion_confidence"]),
                evidence_ids=evidence_ids,
                reasons=[*reasons, "rescue_blocked_metadata"],
            )

            # Determine domain override if candidate lacks one
            target_domain = (
                candidate.context.get("domain")
                or (
                    request.evidence_by_topic
                    and next(
                        (
                            item.metadata.get("domain") or item.metadata.get("project")
                            for items in request.evidence_by_topic.values()
                            for item in items
                            if item.metadata.get("domain") or item.metadata.get("project")
                        ),
                        None,
                    )
                )
                or default_domain
            )

            if dry_run:
                print(
                    f"[DRY-RUN] Would rescue: {dream_run_id}#{candidate_index} "
                    f"entity={candidate.entity_name} domain={target_domain}"
                )
                rescued += 1
                domain_counts[str(target_domain)] = domain_counts.get(str(target_domain), 0) + 1
                continue

            write_result = writer.write_candidate(
                request=request,
                candidate=candidate,
                decision=decision,
                dream_run_id=dream_run_id,
                candidate_index=candidate_index,
                domain_override=str(target_domain),
            )

            if write_result.status == DreamWriteStatus.WRITTEN and write_result.evolution:
                evolution = write_result.evolution
                now_str = datetime.now(UTC).isoformat()
                with conn:
                    conn.execute(
                        """
                        UPDATE dream_candidate_writes
                        SET write_status = ?,
                            write_reason = ?,
                            evolution_outcome = ?,
                            knowledge_id = ?,
                            previous_knowledge_id = ?,
                            created_at = ?
                        WHERE dream_run_id = ? AND candidate_index = ?
                        """,
                        (
                            write_result.status.value,
                            write_result.reason,
                            evolution.outcome.value,
                            str(evolution.record.id),
                            str(evolution.previous_id) if evolution.previous_id else None,
                            now_str,
                            dream_run_id,
                            candidate_index,
                        ),
                    )
                rescued += 1
                domain_counts[str(target_domain)] = domain_counts.get(str(target_domain), 0) + 1
                print(
                    f"Rescued: {dream_run_id}#{candidate_index} -> "
                    f"id={evolution.record.id} domain={target_domain}"
                )
            else:
                errors += 1
                print(
                    f"Failed to write: {dream_run_id}#{candidate_index} "
                    f"status={write_result.status} reason={write_result.reason}"
                )
        except Exception as exc:
            errors += 1
            print(f"Error on {dream_run_id}#{candidate_index}: {exc}")

    conn.close()

    requeued_count = 0
    if requeue_failed and queue_db_path and queue_db_path.exists():
        queue = DreamQueue(queue_db_path)
        requeued_count = queue.requeue_all_failed(limit=100)
        print(f"Requeued {requeued_count} failed jobs in dream queue.")

    summary = {
        "rescued": rescued,
        "errors": errors,
        "domain_counts": domain_counts,
        "requeued_jobs": requeued_count,
        "dry_run": dry_run,
    }
    print(f"\nCompleted: {summary}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audit-db",
        type=Path,
        default=Path("/home/dinhtc/docker-all/cyberbrain-data/dream_audit.sqlite"),
        help="Path to dream_audit.sqlite",
    )
    parser.add_argument(
        "--queue-db",
        type=Path,
        default=Path("/home/dinhtc/docker-all/cyberbrain-data/dream_queue.sqlite"),
        help="Path to dream_queue.sqlite",
    )
    parser.add_argument(
        "--default-domain",
        type=str,
        default="engineering",
        help="Default domain fallback (default: engineering)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without writing to Qdrant or SQLite",
    )
    parser.add_argument(
        "--requeue-failed",
        action="store_true",
        help="Also requeue failed dead-letter jobs in dream queue",
    )
    parser.add_argument("--qdrant-url", default=None)
    parser.add_argument("--embedding-url", default=None)
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    rescue_blocked_candidates(
        audit_db_path=args.audit_db,
        queue_db_path=args.queue_db,
        default_domain=args.default_domain,
        dry_run=args.dry_run,
        requeue_failed=args.requeue_failed,
        qdrant_url=args.qdrant_url,
        embedding_url=args.embedding_url,
        api_key=args.api_key,
    )


if __name__ == "__main__":
    main()
