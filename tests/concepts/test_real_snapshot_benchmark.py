# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.concepts.real_snapshot import run


def _row(
    record_id: str,
    *,
    topic: str,
    entity_name: str,
    origin: str = "ingestion",
    provenance_type: str | None = None,
    verification: str = "tested",
) -> dict:
    return {
        "id": record_id,
        "record_type": "knowledge",
        "content": "Reusable evidence without operational event markers.",
        "summary": "Reusable evidence.",
        "domain": "code",
        "topic": topic,
        "entity_type": "decision",
        "entity_name": entity_name,
        "status": "active",
        "verification": verification,
        "origin": origin,
        "provenance_type": provenance_type,
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_strict_mode_uses_only_shadow_eligible_evidence(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.jsonl"
    _write_jsonl(
        snapshot,
        [
            *[
                _row(f"n{index}", topic="native", entity_name=f"native-{index}")
                for index in range(5)
            ],
            *[
                _row(
                    f"m{index}",
                    topic="migrated",
                    entity_name=f"migrated-{index}",
                    origin="migration",
                    provenance_type="legacy_qdrant",
                )
                for index in range(5)
            ],
        ],
    )

    report = run(snapshot_path=snapshot, mode="strict")

    assert report["selected_evidence_rows"] == 5
    assert report["candidate_count"] == 1
    assert report["registry"]["stability_rate"] == 1.0
    assert report["changes_runtime_behavior"] is False


def test_reviewed_historical_mode_can_include_clean_migrated_evidence(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.jsonl"
    _write_jsonl(
        snapshot,
        [
            *[
                _row(
                    f"m{index}",
                    topic="migrated",
                    entity_name=f"migrated-{index}",
                    origin="migration",
                    provenance_type="legacy_qdrant",
                    verification="unverified",
                )
                for index in range(5)
            ],
        ],
    )

    strict = run(snapshot_path=snapshot, mode="strict")
    reviewed = run(snapshot_path=snapshot, mode="reviewed_historical")

    assert strict["candidate_count"] == 0
    assert reviewed["candidate_count"] == 1
    assert reviewed["promotion_decisions"] == {"reject": 1}


def test_review_manifest_measures_precision_without_changing_discovery(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.jsonl"
    manifest = tmp_path / "reviews.json"
    _write_jsonl(
        snapshot,
        [
            *[
                _row(f"a{index}", topic="good", entity_name=f"good-{index}")
                for index in range(5)
            ],
            *[
                _row(f"b{index}", topic="bad", entity_name=f"bad-{index}")
                for index in range(5)
            ],
        ],
    )
    manifest.write_text(
        json.dumps(
            {
                "reviews": [
                    {
                        "scope_marker": "snapshot:single-owner:global",
                        "domain": "code",
                        "topic": "good",
                        "disposition": "useful_concept",
                    },
                    {
                        "scope_marker": "snapshot:single-owner:global",
                        "domain": "code",
                        "topic": "bad",
                        "disposition": "false_abstraction",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = run(snapshot_path=snapshot, mode="strict", review_manifest=manifest)

    assert report["candidate_count"] == 2
    assert report["reviewed"]["precision"] == 0.5
    assert report["reviewed"]["false_abstraction_rate"] == 0.5
    assert report["reviewed"]["expected_useful_count"] == 1
    assert report["reviewed"]["detected_useful_count"] == 1
    assert report["reviewed"]["useful_recall"] == 1.0
    assert report["reviewed"]["suppressed_reviewed_count"] == 0
    assert report["duplicate_candidate_rate"] == 0.0
