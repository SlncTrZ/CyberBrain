# SPDX-License-Identifier: MPL-2.0
"""Create and verify a coherent F0 production recovery bundle.
Backs up both Qdrant collections + operational SQLite databases + manifest.
Updated: 2026-10-24 13:30
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from cyberbrain.backup.service import BackupService, QdrantSnapshotClient
from cyberbrain.core.settings import Settings


def create_and_verify_bundle(
    *,
    destination: Path,
    qdrant_url: str | None = None,
    api_key: str | None = None,
    sqlite_dir: Path | None = None,
    allow_partial: bool = False,
) -> dict:
    settings = Settings()
    if qdrant_url:
        settings.qdrant_url = qdrant_url
    if api_key:
        settings.qdrant_api_key = api_key

    qdrant_client = QdrantSnapshotClient(
        base_url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )
    service = BackupService(
        qdrant=qdrant_client,
        collections=[settings.knowledge_collection, settings.episodic_collection],
    )

    base_sqlite = sqlite_dir or Path("/home/dinhtc/docker-all/cyberbrain-data")
    sqlite_files = {
        "dream_queue": base_sqlite / "dream_queue.sqlite",
        "dream_audit": base_sqlite / "dream_audit.sqlite",
        "dream_reason_tasks": base_sqlite / "dream_reason_tasks.sqlite",
    }
    missing_sqlite = [
        name for name, path in sqlite_files.items() if not Path(path).is_file()
    ]
    if missing_sqlite and not allow_partial:
        raise FileNotFoundError(
            f"Core operational SQLite databases missing under {base_sqlite}: {missing_sqlite}. "
            "Use --allow-partial if this is intentional."
        )

    existing_sqlite = {
        name: path for name, path in sqlite_files.items() if Path(path).is_file()
    }
    db_names = list(existing_sqlite.keys())
    print(f"Discovered {len(existing_sqlite)} SQLite databases under {base_sqlite}: {db_names}")

    timestamp_dir = destination / datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    print(f"Creating recovery bundle at {timestamp_dir}...")
    manifest = service.create(
        destination=timestamp_dir,
        sqlite_files=existing_sqlite,
    )
    print(f"Created bundle with {len(manifest.files)} files. Validating integrity...")

    # Verification phase
    checks = {}
    for entry in manifest.files:
        filepath = timestamp_dir / entry.filename
        if not filepath.is_file():
            raise FileNotFoundError(f"Missing backup file: {entry.filename}")
        data = filepath.read_bytes()
        size_ok = len(data) == entry.size
        digest = hashlib.sha256(data).hexdigest()
        digest_ok = digest == entry.sha256

        sqlite_integrity = None
        if entry.kind == "sqlite":
            with sqlite3.connect(filepath) as db:
                row = db.execute("PRAGMA quick_check;").fetchone()
                sqlite_integrity = row[0] if row else "unknown"

        checks[entry.filename] = {
            "kind": entry.kind,
            "size": entry.size,
            "size_match": size_ok,
            "sha256": digest,
            "digest_match": digest_ok,
            "sqlite_check": sqlite_integrity,
        }

    all_valid = all(
        c["size_match"]
        and c["digest_match"]
        and (c["sqlite_check"] is None or c["sqlite_check"] == "ok")
        for c in checks.values()
    )
    receipt = {
        "status": "PASS" if all_valid else "FAIL",
        "bundle_path": str(timestamp_dir),
        "created_at": manifest.created_at,
        "files_count": len(manifest.files),
        "checks": checks,
    }
    print("\n=== F0 Bundle Verification Receipt ===")
    print(json.dumps(receipt, indent=2))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("/home/dinhtc/docker-all/cyberbrain-rollouts"),
        help="Root directory for backup bundles",
    )
    parser.add_argument(
        "--sqlite-dir",
        type=Path,
        default=None,
        help="Directory containing operational SQLite files",
    )
    parser.add_argument("--qdrant-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow backup even if some operational SQLite files are missing",
    )
    args = parser.parse_args()

    create_and_verify_bundle(
        destination=args.destination,
        qdrant_url=args.qdrant_url,
        api_key=args.api_key,
        sqlite_dir=args.sqlite_dir,
        allow_partial=args.allow_partial,
    )


if __name__ == "__main__":
    main()
