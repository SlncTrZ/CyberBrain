# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from cyberbrain.backup.service import BackupService, QdrantSnapshotClient
from cyberbrain.core.settings import Settings


def build_service(settings: Settings) -> BackupService:
    return BackupService(
        qdrant=QdrantSnapshotClient(
            base_url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        ),
        collections=[settings.knowledge_collection, settings.episodic_collection],
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="cyberbrain-backup")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup")
    backup.add_argument("destination")

    restore = subparsers.add_parser("restore")
    restore.add_argument("source")
    restore.add_argument(
        "--confirm-overwrite",
        action="store_true",
        help="Required because restore overwrites current Qdrant collections and SQLite state.",
    )

    args = parser.parse_args()
    settings = Settings()
    settings.validate_runtime()
    service = build_service(settings)

    if args.command == "backup":
        manifest = service.create(
            destination=args.destination,
            sqlite_files={
                "dream_queue": settings.dream_queue_db,
                "dream_audit": settings.dream_audit_db,
            },
        )
    else:
        if not args.confirm_overwrite:
            parser.error("restore requires --confirm-overwrite")
        manifest = service.restore(
            source=args.source,
            sqlite_destinations={
                "dream_queue": settings.dream_queue_db,
                "dream_audit": settings.dream_audit_db,
            },
        )

    print(json.dumps(asdict(manifest), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
