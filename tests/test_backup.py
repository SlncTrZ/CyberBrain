# SPDX-License-Identifier: MPL-2.0

import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from cyberbrain.backup.service import BackupService, QdrantSnapshotClient


class FakeSnapshotClient:
    def __init__(self) -> None:
        self.restored: list[tuple[str, str, str]] = []

    def create_and_download(self, *, collection: str, destination: Path) -> Path:
        path = destination / f"{collection}.snapshot"
        path.write_bytes(f"snapshot:{collection}".encode())
        return path

    def restore_uploaded(self, *, collection: str, snapshot: Path, checksum: str) -> None:
        self.restored.append((collection, snapshot.name, checksum))


def _make_sqlite(path: Path, value: str) -> None:
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS items (value TEXT NOT NULL)")
        db.execute("DELETE FROM items")
        db.execute("INSERT INTO items(value) VALUES (?)", (value,))


def _read_sqlite(path: Path) -> str:
    with sqlite3.connect(path) as db:
        return str(db.execute("SELECT value FROM items").fetchone()[0])


def test_backup_rejects_missing_sqlite_source(tmp_path) -> None:
    missing = tmp_path / "missing.sqlite"
    service = BackupService(qdrant=FakeSnapshotClient(), collections=[])

    with pytest.raises(FileNotFoundError, match="SQLite backup source is missing"):
        service.create(
            destination=tmp_path / "backup",
            sqlite_files={"dream_queue": missing},
        )

    assert not missing.exists()


def test_backup_and_restore_sqlite_with_manifest_checksums(tmp_path) -> None:
    queue = tmp_path / "queue.sqlite"
    audit = tmp_path / "audit.sqlite"
    _make_sqlite(queue, "queue-original")
    _make_sqlite(audit, "audit-original")

    fake = FakeSnapshotClient()
    service = BackupService(qdrant=fake, collections=["knowledge", "episodic"])
    backup_dir = tmp_path / "backup"
    manifest = service.create(
        destination=backup_dir,
        sqlite_files={"dream_queue": queue, "dream_audit": audit},
    )

    assert manifest.format_version == 1
    assert len(manifest.files) == 4
    assert (backup_dir / "manifest.json").is_file()

    _make_sqlite(queue, "queue-mutated")
    _make_sqlite(audit, "audit-mutated")
    service.restore(
        source=backup_dir,
        sqlite_destinations={"dream_queue": queue, "dream_audit": audit},
    )

    assert _read_sqlite(queue) == "queue-original"
    assert _read_sqlite(audit) == "audit-original"
    assert [item[0] for item in fake.restored] == ["knowledge", "episodic"]


def test_restore_rejects_tampered_backup_before_mutation(tmp_path) -> None:
    queue = tmp_path / "queue.sqlite"
    _make_sqlite(queue, "original")
    fake = FakeSnapshotClient()
    service = BackupService(qdrant=fake, collections=["knowledge"])
    backup_dir = tmp_path / "backup"
    service.create(destination=backup_dir, sqlite_files={"dream_queue": queue})

    (backup_dir / "knowledge.snapshot").write_bytes(b"tampered")

    with pytest.raises(ValueError, match="checksum mismatch|size mismatch"):
        service.restore(
            source=backup_dir,
            sqlite_destinations={"dream_queue": queue},
        )

    assert fake.restored == []


def test_qdrant_snapshot_client_uses_collection_snapshot_endpoints(tmp_path) -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST" and request.url.path == "/collections/knowledge/snapshots":
            return httpx.Response(
                200,
                json={"status": "ok", "result": {"name": "snapshot-1.snapshot"}},
                request=request,
            )
        if request.method == "GET":
            return httpx.Response(200, content=b"snapshot-bytes", request=request)
        if request.url.path.endswith("/snapshots/upload"):
            assert request.url.params["priority"] == "snapshot"
            assert request.url.params["wait"] == "true"
            assert "checksum" in request.url.params
            return httpx.Response(
                200,
                json={"status": "ok", "result": True},
                request=request,
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    snapshots = QdrantSnapshotClient(base_url="http://qdrant:6333", client=client)
    path = snapshots.create_and_download(collection="knowledge", destination=tmp_path)
    assert path.read_bytes() == b"snapshot-bytes"

    checksum = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    snapshots.restore_uploaded(collection="knowledge", snapshot=path, checksum=checksum)

    assert calls == [
        ("POST", "/collections/knowledge/snapshots"),
        ("GET", "/collections/knowledge/snapshots/snapshot-1.snapshot"),
        ("POST", "/collections/knowledge/snapshots/upload"),
    ]


def test_manifest_is_plain_json_without_credentials(tmp_path) -> None:
    sqlite_path = tmp_path / "queue.sqlite"
    _make_sqlite(sqlite_path, "x")
    service = BackupService(qdrant=FakeSnapshotClient(), collections=[])
    backup_dir = tmp_path / "backup"
    service.create(destination=backup_dir, sqlite_files={"dream_queue": sqlite_path})

    raw = json.loads((backup_dir / "manifest.json").read_text())
    assert set(raw) == {"format_version", "created_at", "files"}
