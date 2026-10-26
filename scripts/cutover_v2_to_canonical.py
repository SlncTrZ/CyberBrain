# SPDX-License-Identifier: MPL-2.0
"""Production Collection Cutover Tool: Stage Collections -> Canonical Collections.

Copies and validates Qdrant collections from _v2_stage to canonical names
(cyberbrain_knowledge, cyberbrain_episodic) with exact snapshot integrity and count verification.
Updated: 2026-10-26 11:00
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cyberbrain.backup.service import QdrantSnapshotClient
from cyberbrain.core.settings import Settings
from cyberbrain.relations.storage import RelationIndex
from cyberbrain.storage.qdrant import QdrantRepository
from cyberbrain.tenancy.durable import bind_job_authority


def cutover_collections(
    *,
    qdrant_url: str,
    api_key: str | None = None,
    source_knowledge: str = "cyberbrain_knowledge_v2_stage",
    source_episodic: str = "cyberbrain_episodic_v2_stage",
    target_knowledge: str = "cyberbrain_knowledge",
    target_episodic: str = "cyberbrain_episodic",
    dry_run: bool = False,
) -> dict[str, Any]:
    client = QdrantSnapshotClient(base_url=qdrant_url, api_key=api_key, timeout_seconds=300.0)
    repo = QdrantRepository(base_url=qdrant_url, api_key=api_key)

    # 1. Preflight check
    src_k_info = repo.collection_info(source_knowledge)
    src_e_info = repo.collection_info(source_episodic)

    if src_k_info is None:
        raise ValueError(f"Source knowledge collection not found: {source_knowledge}")
    if src_e_info is None:
        raise ValueError(f"Source episodic collection not found: {source_episodic}")

    src_k_points = src_k_info.get("points_count", 0)
    src_e_points = src_e_info.get("points_count", 0)

    print("Source collections preflight:")
    print(f"  {source_knowledge}: {src_k_points} points (status={src_k_info.get('status')})")
    print(f"  {source_episodic}: {src_e_points} points (status={src_e_info.get('status')})")

    if dry_run:
        print("\n[DRY-RUN] Preflight passed. No snapshots created or collections modified.")
        return {
            "status": "DRY_RUN_PASS",
            "source_knowledge": {source_knowledge: src_k_points},
            "source_episodic": {source_episodic: src_e_points},
        }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        print(f"\n1. Snapshotting and downloading '{source_knowledge}'...")
        k_snap_path = client.create_and_download(collection=source_knowledge, destination=tmp_path)
        k_data = k_snap_path.read_bytes()
        k_sha256 = hashlib.sha256(k_data).hexdigest()
        print(f"   Downloaded {len(k_data):,} bytes (SHA256: {k_sha256[:16]}...)")

        print(f"\n2. Snapshotting and downloading '{source_episodic}'...")
        e_snap_path = client.create_and_download(collection=source_episodic, destination=tmp_path)
        e_data = e_snap_path.read_bytes()
        e_sha256 = hashlib.sha256(e_data).hexdigest()
        print(f"   Downloaded {len(e_data):,} bytes (SHA256: {e_sha256[:16]}...)")

        # 3. Restore to target collections
        print(f"\n3. Restoring snapshot into target collection '{target_knowledge}'...")
        client.restore_uploaded(
            collection=target_knowledge, snapshot=k_snap_path, checksum=k_sha256
        )

        print(f"\n4. Restoring snapshot into target collection '{target_episodic}'...")
        client.restore_uploaded(
            collection=target_episodic, snapshot=e_snap_path, checksum=e_sha256
        )

    # 4. Verify postconditions
    tgt_k_info = repo.collection_info(target_knowledge) or {}
    tgt_e_info = repo.collection_info(target_episodic) or {}

    tgt_k_points = tgt_k_info.get("points_count", 0)
    tgt_e_points = tgt_e_info.get("points_count", 0)

    print("\nTarget collections post-restore verification:")
    print(f"  {target_knowledge}: {tgt_k_points} points (expected: {src_k_points})")
    print(f"  {target_episodic}: {tgt_e_points} points (expected: {src_e_points})")

    k_match = tgt_k_points == src_k_points
    e_match = tgt_e_points == src_e_points

    # 5. Verify payload indexes on target knowledge
    index = RelationIndex(repo, target_knowledge, target_episodic)
    index_ok = True
    try:
        index.verify_indexes()
    except Exception as exc:
        print(f"   Note: Relation indexes need preparation on {target_knowledge}: {exc}")
        try:
            with bind_job_authority(None):
                index.prepare_indexes()
            print("   Relation indexes prepared successfully.")
        except Exception as p_exc:
            print(f"   Warning: Could not prepare indexes: {p_exc}")
            index_ok = False

    receipt = {
        "status": "PASS" if (k_match and e_match and index_ok) else "FAIL",
        "timestamp": datetime.now(UTC).isoformat(),
        "source_knowledge": {"name": source_knowledge, "points": src_k_points},
        "source_episodic": {"name": source_episodic, "points": src_e_points},
        "target_knowledge": {"name": target_knowledge, "points": tgt_k_points, "match": k_match},
        "target_episodic": {"name": target_episodic, "points": tgt_e_points, "match": e_match},
        "relation_index_verified": index_ok,
    }
    print("\n=== Collection Cutover Receipt ===")
    print(json.dumps(receipt, indent=2))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-url", default=None, help="Qdrant API base URL")
    parser.add_argument("--api-key", default=None, help="Qdrant API key")
    parser.add_argument("--source-knowledge", default="cyberbrain_knowledge_v2_stage")
    parser.add_argument("--source-episodic", default="cyberbrain_episodic_v2_stage")
    parser.add_argument("--target-knowledge", default="cyberbrain_knowledge")
    parser.add_argument("--target-episodic", default="cyberbrain_episodic")
    parser.add_argument("--dry-run", action="store_true", help="Run preflight check only")
    args = parser.parse_args()

    settings = Settings()
    qdrant_url = args.qdrant_url or settings.qdrant_url
    api_key = args.api_key or settings.qdrant_api_key

    cutover_collections(
        qdrant_url=qdrant_url,
        api_key=api_key,
        source_knowledge=args.source_knowledge,
        source_episodic=args.source_episodic,
        target_knowledge=args.target_knowledge,
        target_episodic=args.target_episodic,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
