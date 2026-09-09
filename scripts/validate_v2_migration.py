# SPDX-License-Identifier: MPL-2.0
"""Independent validation for schema-V2 union migration."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from cyberbrain.core.content import normalize_content
from cyberbrain.schemas.models import (
    EpisodeRecord,
    IdentityTrust,
    KnowledgeRecord,
    KnowledgeRecordClass,
    LifecycleState,
)
from scripts.stage_v2_migration import QdrantClient, _by_id


def _load(client: QdrantClient, name: str) -> dict[str, dict[str, Any]]:
    return _by_id(client.scroll_all(name))


def _valid_raw_episode(point: dict[str, Any]) -> bool:
    payload = dict(point.get("payload") or {})
    return bool(
        str(payload.get("content") or "").strip()
        and str(payload.get("session_id") or "").strip()
        and payload.get("timestamp") is not None
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--knowledge-primary", default="cyberbrain_knowledge_v1_stage")
    parser.add_argument("--episodic-primary", default="cyberbrain_episodic_v1_stage")
    parser.add_argument("--knowledge-raw", default="cyberbrain_knowledge")
    parser.add_argument("--episodic-raw", default="cyberbrain_episodic")
    parser.add_argument("--knowledge-target", default="cyberbrain_knowledge_v2_stage")
    parser.add_argument("--episodic-target", default="cyberbrain_episodic_v2_stage")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    client = QdrantClient()
    pk = _load(client, args.knowledge_primary)
    pe = _load(client, args.episodic_primary)
    rk = _load(client, args.knowledge_raw)
    re = _load(client, args.episodic_raw)
    tk = _load(client, args.knowledge_target)
    te = _load(client, args.episodic_target)

    source_union = set(pk) | set(pe) | set(rk) | set(re)
    target_union = set(tk) | set(te)
    if target_union != source_union:
        raise SystemExit(
            f"target union mismatch missing={len(source_union - target_union)} "
            f"extra={len(target_union - source_union)}"
        )
    if set(tk) & set(te):
        raise SystemExit("target Knowledge/Episodic ID overlap")

    counters: Counter[str] = Counter()
    for point_id, point in tk.items():
        record = KnowledgeRecord.model_validate(point["payload"])
        if str(record.id) != point_id or record.schema_version != 2:
            raise SystemExit(f"invalid target Knowledge identity/schema: {point_id}")
        if record.record_class is KnowledgeRecordClass.MIGRATION_QUARANTINE:
            counters["quarantine"] += 1
            if record.ordinary_recall or record.lifecycle_state is not LifecycleState.SUPPRESSED:
                raise SystemExit(f"quarantine record is recall-visible: {point_id}")
        if (
            record.record_class is KnowledgeRecordClass.SELF_MODEL_HYPOTHESIS
            and record.ordinary_recall
        ):
            raise SystemExit(f"self-model hypothesis leaked to ordinary recall: {point_id}")
        counters[f"knowledge_identity_trust:{record.identity_trust.value}"] += 1
        _validate_vector(point_id, point, pk.get(point_id) or rk.get(point_id) or re.get(point_id))
        _validate_content(point_id, point, pk.get(point_id) or rk.get(point_id) or re.get(point_id))

    for point_id, point in te.items():
        record = EpisodeRecord.model_validate(point["payload"])
        if str(record.id) != point_id or record.schema_version != 2:
            raise SystemExit(f"invalid target Episode identity/schema: {point_id}")
        if record.source in {"cognitive_prediction", "cognitive_outcome"} and point_id in pe:
            if record.identity_trust is IdentityTrust.AUTHENTICATED:
                raise SystemExit(f"pre-P3 cognitive evidence was retroactively trusted: {point_id}")
        counters[f"episode_identity_trust:{record.identity_trust.value}"] += 1
        source = pe.get(point_id) or re.get(point_id)
        _validate_vector(point_id, point, source)
        _validate_content(point_id, point, source)

    primary_ids = set(pk) | set(pe)
    raw_knowledge_delta = set(rk) - primary_ids
    raw_episode_delta = set(re) - primary_ids
    expected_quarantine = sum(
        not _valid_raw_episode(re[point_id]) for point_id in raw_episode_delta
    )
    if counters["quarantine"] < expected_quarantine:
        raise SystemExit("not all malformed raw Episodes were quarantined")

    report = {
        "source_union": len(source_union),
        "target_union": len(target_union),
        "target_knowledge": len(tk),
        "target_episodic": len(te),
        "raw_knowledge_delta": len(raw_knowledge_delta),
        "raw_episode_delta": len(raw_episode_delta),
        "expected_minimum_quarantine": expected_quarantine,
        "counters": dict(counters),
        "status": "pass",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _validate_vector(
    point_id: str,
    target: dict[str, Any],
    source: dict[str, Any] | None,
) -> None:
    if source is None:
        raise SystemExit(f"target point has no source: {point_id}")
    if target.get("vector") != source.get("vector"):
        raise SystemExit(f"vector changed during migration: {point_id}")


def _validate_content(
    point_id: str,
    target: dict[str, Any],
    source: dict[str, Any] | None,
) -> None:
    if source is None:
        raise SystemExit(f"target point has no source content: {point_id}")
    source_content = normalize_content(
        (source.get("payload") or {}).get("content") or f"Legacy record {point_id}"
    )
    target_content = normalize_content((target.get("payload") or {}).get("content"))
    if source_content != target_content:
        raise SystemExit(f"content changed during migration: {point_id}")


if __name__ == "__main__":
    main()
