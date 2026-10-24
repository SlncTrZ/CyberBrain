# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cyberbrain.backup.service import BackupFile, BackupManifest
from scripts.create_f0_recovery_bundle import create_and_verify_bundle


def test_create_and_verify_bundle_mock(tmp_path: Path):
    dest = tmp_path / "backups"
    sqlite_dir = tmp_path / "data"
    sqlite_dir.mkdir(parents=True)

    # Create dummy sqlite db
    db_path = sqlite_dir / "dream_queue.sqlite"
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE test (id int);")
        db.execute("INSERT INTO test VALUES (1);")

    # Mock BackupService and QdrantSnapshotClient inside the script
    mock_service = MagicMock()

    def fake_create(destination, sqlite_files):
        p = Path(destination)
        p.mkdir(parents=True, exist_ok=True)
        # copy dummy sqlite
        copied_sqlite = p / "dream_queue.sqlite"
        copied_sqlite.write_bytes(db_path.read_bytes())
        # create dummy snapshot
        snap = p / "cyberbrain_knowledge.snapshot"
        snap.write_bytes(b"dummy snapshot")

        import hashlib
        files = [
            BackupFile(
                kind="sqlite",
                source="dream_queue",
                filename="dream_queue.sqlite",
                sha256=hashlib.sha256(copied_sqlite.read_bytes()).hexdigest(),
                size=len(copied_sqlite.read_bytes()),
            ),
            BackupFile(
                kind="qdrant_collection",
                source="cyberbrain_knowledge",
                filename="cyberbrain_knowledge.snapshot",
                sha256=hashlib.sha256(b"dummy snapshot").hexdigest(),
                size=len(b"dummy snapshot"),
            ),
        ]
        manifest = BackupManifest(format_version=1, created_at="2026-10-24T00:00:00Z", files=files)
        (p / "manifest.json").write_text(json.dumps({
            "format_version": 1,
            "created_at": manifest.created_at,
            "files": [f.__dict__ for f in files]
        }))
        return manifest

    mock_service.create.side_effect = fake_create

    import scripts.create_f0_recovery_bundle
    orig_service = scripts.create_f0_recovery_bundle.BackupService
    scripts.create_f0_recovery_bundle.BackupService = MagicMock(return_value=mock_service)
    try:
        # Default should fail-closed because dream_audit and dream_reason_tasks are missing
        with pytest.raises(FileNotFoundError, match="Core operational SQLite databases missing"):
            create_and_verify_bundle(
                destination=dest,
                sqlite_dir=sqlite_dir,
                qdrant_url="http://fake:6333",
            )

        # With allow_partial=True it succeeds
        receipt = create_and_verify_bundle(
            destination=dest,
            sqlite_dir=sqlite_dir,
            qdrant_url="http://fake:6333",
            allow_partial=True,
        )
        assert receipt["status"] == "PASS"
        assert receipt["files_count"] == 2
        assert "dream_queue.sqlite" in receipt["checks"]
        assert receipt["checks"]["dream_queue.sqlite"]["sqlite_check"] == "ok"
    finally:
        scripts.create_f0_recovery_bundle.BackupService = orig_service
