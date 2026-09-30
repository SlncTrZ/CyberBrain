# SPDX-License-Identifier: MPL-2.0
"""Read-only, bounded Dream review diagnostics; no promotion authority."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


def review_backlog(path: str | Path, *, limit: int = 5000, now: datetime | None = None) -> dict:
    if not 1 <= limit <= 10000:
        raise ValueError("limit must be between 1 and 10000")
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("now must include a timezone")
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        base = """
            FROM dream_candidate_decisions d
            LEFT JOIN dream_candidate_reviews r
            ON r.dream_run_id=d.dream_run_id AND r.candidate_index=d.candidate_index
            WHERE d.decision='review' AND r.dream_run_id IS NULL
        """
        total = connection.execute("SELECT COUNT(*) " + base).fetchone()[0]
        rows = connection.execute(
            "SELECT d.* " + base +
            " ORDER BY d.created_at, d.dream_run_id, d.candidate_index LIMIT ?", (limit,),
        ).fetchall()
    reasons = Counter()
    fingerprints = Counter()
    content_fingerprints = Counter()
    ranked = []
    for row in rows:
        candidate = json.loads(row["candidate_json"])
        evidence = sorted(set(json.loads(row["evidence_ids_json"])))
        # A grouping suggestion does not imply truth or interchangeable evidence.
        content = " ".join(
            unicodedata.normalize("NFKC", candidate.get("content", "")).casefold().split()
        )
        identity = [
            candidate.get("entity_type"), candidate.get("entity_name"),
            candidate.get("context", {}), content,
        ]
        fingerprint = hashlib.sha256(json.dumps(
            [identity, evidence], sort_keys=True, ensure_ascii=False,
        ).encode()).hexdigest()
        content_fingerprint = hashlib.sha256(json.dumps(
            identity, sort_keys=True, ensure_ascii=False,
        ).encode()).hexdigest()
        fingerprints[fingerprint] += 1
        content_fingerprints[content_fingerprint] += 1
        reasons.update(json.loads(row["reasons_json"]))
        created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
        if created.tzinfo is None:
            raise ValueError("review timestamp must include a timezone")
        age = max(0.0, (instant - created).total_seconds() / 86400)
        strength = float(row["evidence_strength"])
        priority = round(strength + min(age / 30, 1.0) * 0.25, 6)
        ranked.append({
            "dream_run_id": row["dream_run_id"], "candidate_index": row["candidate_index"],
            "created_at": row["created_at"], "age_days": round(age, 2),
            "evidence_strength": strength, "evidence_count": len(evidence),
            "fingerprint": fingerprint, "priority": priority,
        })
    ranked.sort(key=lambda row: (
        -row["priority"], row["created_at"], row["dream_run_id"], row["candidate_index"],
    ))
    return {
        "unresolved_total": total, "sampled": len(rows), "complete_scan": total <= limit,
        "duplicate_content_and_evidence": sum(n - 1 for n in fingerprints.values()),
        "repeated_content": sum(n - 1 for n in content_fingerprints.values()),
        "reason_counts": dict(sorted(reasons.items())),
        "weak_evidence_count": sum(row["evidence_strength"] < 0.5 for row in ranked),
        "oldest_age_days": max((row["age_days"] for row in ranked), default=0),
        "review_queue": ranked,
        "mutates_data": False,
        "priority_is_not_promotion": True,
    }
