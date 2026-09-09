# SPDX-License-Identifier: MPL-2.0
"""Stage a complete schema-V2 union from canonical V1 + raw legacy Qdrant sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from cyberbrain.migrations.v2 import V2MetadataNormalizer
from cyberbrain.schemas.models import EpisodeRecord, KnowledgeRecord, KnowledgeRecordClass


class QdrantClient:
    def __init__(self) -> None:
        self.base_url = os.environ["QDRANT_URL"].rstrip("/")
        api_key = os.getenv("QDRANT_API_KEY")
        self.headers = {"api-key": api_key} if api_key else {}
        self.client = httpx.Client(headers=self.headers, timeout=60)

    def collection_exists(self, name: str) -> bool:
        response = self.client.get(f"{self.base_url}/collections/{name}")
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True

    def create_like(self, *, source: str, target: str) -> None:
        if self.collection_exists(target):
            return
        source_info = self.client.get(f"{self.base_url}/collections/{source}")
        source_info.raise_for_status()
        params = source_info.json()["result"]["config"]["params"]
        body = {
            "vectors": params["vectors"],
            "on_disk_payload": bool(params.get("on_disk_payload", True)),
        }
        response = self.client.put(f"{self.base_url}/collections/{target}", json=body)
        response.raise_for_status()

    def scroll_all(self, collection: str, *, with_vector: bool = True) -> list[dict[str, Any]]:
        points: list[dict[str, Any]] = []
        offset: Any = None
        while True:
            body: dict[str, Any] = {
                "limit": 512,
                "with_payload": True,
                "with_vector": with_vector,
            }
            if offset is not None:
                body["offset"] = offset
            response = self.client.post(
                f"{self.base_url}/collections/{collection}/points/scroll",
                json=body,
            )
            response.raise_for_status()
            result = response.json()["result"]
            batch = list(result.get("points") or [])
            points.extend(batch)
            offset = result.get("next_page_offset")
            if offset is None:
                return points

    def upsert(self, collection: str, points: list[dict[str, Any]]) -> None:
        for start in range(0, len(points), 64):
            batch = points[start : start + 64]
            response = self.client.put(
                f"{self.base_url}/collections/{collection}/points",
                params={"wait": "true"},
                json={"points": batch},
                timeout=120,
            )
            response.raise_for_status()

    def count(self, collection: str) -> int:
        response = self.client.post(
            f"{self.base_url}/collections/{collection}/points/count",
            json={"exact": True},
        )
        response.raise_for_status()
        return int(response.json()["result"]["count"])


def _by_id(points: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(point["id"]): point for point in points}


def _fingerprint(collections: dict[str, list[dict[str, Any]]]) -> str:
    digest = hashlib.sha256()
    for collection in sorted(collections):
        digest.update(collection.encode())
        for point in sorted(collections[collection], key=lambda item: str(item["id"])):
            digest.update(str(point["id"]).encode())
            payload = json.dumps(
                point.get("payload") or {},
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            digest.update(payload.encode())
            vector = json.dumps(
                point.get("vector"),
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            digest.update(vector.encode())
    return digest.hexdigest()


def _source_snapshot(
    client: QdrantClient, args: argparse.Namespace
) -> dict[str, list[dict[str, Any]]]:
    return {
        args.knowledge_primary: client.scroll_all(args.knowledge_primary),
        args.episodic_primary: client.scroll_all(args.episodic_primary),
        args.knowledge_raw: client.scroll_all(args.knowledge_raw),
        args.episodic_raw: client.scroll_all(args.episodic_raw),
    }


def _map_union(
    snapshot: dict[str, list[dict[str, Any]]],
    *,
    args: argparse.Namespace,
    migrated_at: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    normalizer = V2MetadataNormalizer()
    primary_knowledge = _by_id(snapshot[args.knowledge_primary])
    primary_episodic = _by_id(snapshot[args.episodic_primary])
    raw_knowledge = _by_id(snapshot[args.knowledge_raw])
    raw_episodic = _by_id(snapshot[args.episodic_raw])
    primary_ids = set(primary_knowledge) | set(primary_episodic)
    if set(primary_knowledge) & set(primary_episodic):
        raise RuntimeError("primary Knowledge/Episodic collections contain overlapping point IDs")

    target_knowledge: dict[str, dict[str, Any]] = {}
    target_episodic: dict[str, dict[str, Any]] = {}
    counters: Counter[str] = Counter()

    for point_id, point in primary_knowledge.items():
        record = normalizer.normalize_knowledge(
            dict(point.get("payload") or {}),
            source_collection=args.knowledge_primary,
            migrated_at=migrated_at,
        )
        target_knowledge[point_id] = _target_point(point, record.model_dump(mode="json"))
        counters["primary_knowledge"] += 1

    for point_id, point in primary_episodic.items():
        record = normalizer.normalize_episode(
            dict(point.get("payload") or {}),
            source_collection=args.episodic_primary,
            migrated_at=migrated_at,
        )
        target_episodic[point_id] = _target_point(point, record.model_dump(mode="json"))
        counters["primary_episodic"] += 1

    for point_id, point in raw_knowledge.items():
        if point_id in primary_ids:
            continue
        record = normalizer.raw_legacy_knowledge(
            point,
            source_collection=args.knowledge_raw,
            migrated_at=migrated_at,
        )
        target_knowledge[point_id] = _target_point(point, record.model_dump(mode="json"))
        counters["raw_knowledge_delta"] += 1
        if record.record_class is KnowledgeRecordClass.MIGRATION_QUARANTINE:
            counters["quarantine"] += 1

    for point_id, point in raw_episodic.items():
        if point_id in primary_ids:
            continue
        record = normalizer.raw_legacy_episode(
            point,
            source_collection=args.episodic_raw,
            migrated_at=migrated_at,
        )
        if isinstance(record, EpisodeRecord):
            target_episodic[point_id] = _target_point(point, record.model_dump(mode="json"))
            counters["raw_episodic_delta"] += 1
        else:
            target_knowledge[point_id] = _target_point(point, record.model_dump(mode="json"))
            counters["raw_episode_quarantine"] += 1
            counters["quarantine"] += 1

    target_ids = set(target_knowledge) | set(target_episodic)
    source_union = (
        set(primary_knowledge) | set(primary_episodic) | set(raw_knowledge) | set(raw_episodic)
    )
    if target_ids != source_union:
        missing = sorted(source_union - target_ids)
        extra = sorted(target_ids - source_union)
        raise RuntimeError(f"V2 union coverage mismatch missing={missing[:5]} extra={extra[:5]}")
    if set(target_knowledge) & set(target_episodic):
        raise RuntimeError("V2 target Knowledge/Episodic IDs overlap")

    report = {
        "counts": dict(counters),
        "source_union": len(source_union),
        "target_knowledge": len(target_knowledge),
        "target_episodic": len(target_episodic),
        "target_union": len(target_ids),
    }
    return list(target_knowledge.values()), list(target_episodic.values()), report


def _migration_complete(report: dict[str, Any] | None) -> bool:
    if report is None:
        return False
    return bool(
        report.get("source_stable")
        and report.get("target_knowledge_count") == report.get("target_knowledge")
        and report.get("target_episodic_count") == report.get("target_episodic")
    )


def _target_point(source: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    vector = source.get("vector")
    if not isinstance(vector, list) or not vector:
        raise RuntimeError(f"source point {source.get('id')} has no vector")
    return {"id": str(source["id"]), "vector": vector, "payload": payload}


def _validate_payloads(
    knowledge: list[dict[str, Any]], episodic: list[dict[str, Any]]
) -> dict[str, Any]:
    identity_trust: Counter[str] = Counter()
    lifecycle: Counter[str] = Counter()
    record_classes: Counter[str] = Counter()
    for point in knowledge:
        record = KnowledgeRecord.model_validate(point["payload"])
        if str(record.id) != str(point["id"]) or record.schema_version != 2:
            raise RuntimeError("invalid V2 Knowledge ID/schema")
        identity_trust[record.identity_trust.value] += 1
        lifecycle[record.lifecycle_state.value] += 1
        record_classes[record.record_class.value] += 1
    for point in episodic:
        record = EpisodeRecord.model_validate(point["payload"])
        if str(record.id) != str(point["id"]) or record.schema_version != 2:
            raise RuntimeError("invalid V2 Episode ID/schema")
        identity_trust[record.identity_trust.value] += 1
        lifecycle[record.lifecycle_state.value] += 1
    return {
        "identity_trust": dict(identity_trust),
        "lifecycle_state": dict(lifecycle),
        "knowledge_record_class": dict(record_classes),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--knowledge-primary", default="cyberbrain_knowledge_v1_stage")
    parser.add_argument("--episodic-primary", default="cyberbrain_episodic_v1_stage")
    parser.add_argument("--knowledge-raw", default="cyberbrain_knowledge")
    parser.add_argument("--episodic-raw", default="cyberbrain_episodic")
    parser.add_argument("--knowledge-target", default="cyberbrain_knowledge_v2_stage")
    parser.add_argument("--episodic-target", default="cyberbrain_episodic_v2_stage")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--max-passes", type=int, default=3)
    args = parser.parse_args()
    if args.max_passes < 1:
        raise SystemExit("--max-passes must be >= 1")

    client = QdrantClient()
    client.create_like(source=args.knowledge_primary, target=args.knowledge_target)
    client.create_like(source=args.episodic_primary, target=args.episodic_target)

    final_report: dict[str, Any] | None = None
    for pass_number in range(1, args.max_passes + 1):
        started = datetime.now(UTC)
        before = _source_snapshot(client, args)
        before_fingerprint = _fingerprint(before)
        knowledge, episodic, report = _map_union(before, args=args, migrated_at=started)
        validation = _validate_payloads(knowledge, episodic)
        client.upsert(args.knowledge_target, knowledge)
        client.upsert(args.episodic_target, episodic)
        after = _source_snapshot(client, args)
        after_fingerprint = _fingerprint(after)
        report.update(
            {
                "pass": pass_number,
                "migrated_at": started.isoformat(),
                "source_fingerprint_before": before_fingerprint,
                "source_fingerprint_after": after_fingerprint,
                "source_stable": before_fingerprint == after_fingerprint,
                "target_knowledge_count": client.count(args.knowledge_target),
                "target_episodic_count": client.count(args.episodic_target),
                "validation": validation,
            }
        )
        final_report = report
        if _migration_complete(report):
            break
    if not _migration_complete(final_report):
        if final_report is None or not final_report.get("source_stable"):
            raise SystemExit("source collections did not stabilize during V2 migration")
        raise SystemExit(
            "V2 target collections did not converge to expected counts during migration"
        )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(final_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(final_report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
