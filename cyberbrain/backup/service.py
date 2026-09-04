# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from cyberbrain.core.errors import StorageError


@dataclass(frozen=True)
class BackupFile:
    kind: str
    source: str
    filename: str
    sha256: str
    size: int


@dataclass(frozen=True)
class BackupManifest:
    format_version: int
    created_at: str
    files: list[BackupFile]


class QdrantSnapshotClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {}
        if api_key:
            self._headers["api-key"] = api_key
        self._timeout = timeout_seconds
        self._client = client

    def create_and_download(self, *, collection: str, destination: Path) -> Path:
        response = self._request(
            "POST",
            f"/collections/{collection}/snapshots",
        )
        result = response.get("result") or {}
        name = str(result.get("name") or "").strip()
        if not name:
            raise StorageError("Qdrant snapshot response is missing snapshot name")

        target = destination / f"{collection}.snapshot"
        raw = self._send(
            "GET",
            f"/collections/{collection}/snapshots/{name}",
        )
        try:
            raw.raise_for_status()
        except httpx.HTTPError as exc:
            raise StorageError(f"Qdrant snapshot download failed for {collection}: {exc}") from exc
        target.write_bytes(raw.content)
        return target

    def restore_uploaded(self, *, collection: str, snapshot: Path, checksum: str) -> None:
        with snapshot.open("rb") as handle:
            response = self._send(
                "POST",
                f"/collections/{collection}/snapshots/upload",
                params={"wait": "true", "priority": "snapshot", "checksum": checksum},
                files={"snapshot": (snapshot.name, handle, "application/octet-stream")},
            )
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise StorageError(f"Qdrant snapshot restore failed for {collection}: {exc}") from exc
        if payload.get("status") != "ok" or payload.get("result") is not True:
            raise StorageError(f"Qdrant snapshot restore failed for {collection}")

    def _request(self, method: str, path: str) -> dict:
        response = self._send(method, path)
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise StorageError(f"Qdrant snapshot request failed: {method} {path}: {exc}") from exc
        if payload.get("status") != "ok":
            raise StorageError(f"Qdrant snapshot request failed: {method} {path}")
        return payload

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:  # noqa: ANN003
        request_kwargs = {"headers": self._headers, "timeout": self._timeout, **kwargs}
        try:
            if self._client is not None:
                return self._client.request(method, f"{self._base_url}{path}", **request_kwargs)
            return httpx.request(method, f"{self._base_url}{path}", **request_kwargs)
        except httpx.HTTPError as exc:
            raise StorageError(f"Qdrant snapshot transport failed: {method} {path}") from exc


class BackupService:
    def __init__(self, *, qdrant: QdrantSnapshotClient, collections: list[str]) -> None:
        self._qdrant = qdrant
        self._collections = list(collections)

    def create(
        self,
        *,
        destination: str | Path,
        sqlite_files: dict[str, str | Path],
    ) -> BackupManifest:
        root = Path(destination)
        root.mkdir(parents=True, exist_ok=False)
        files: list[BackupFile] = []

        for collection in self._collections:
            path = self._qdrant.create_and_download(collection=collection, destination=root)
            files.append(self._file_entry("qdrant_collection", collection, path))

        for logical_name, source in sqlite_files.items():
            target = root / f"{logical_name}.sqlite"
            self._backup_sqlite(Path(source), target)
            files.append(self._file_entry("sqlite", logical_name, target))

        manifest = BackupManifest(
            format_version=1,
            created_at=datetime.now(UTC).isoformat(),
            files=files,
        )
        (root / "manifest.json").write_text(
            json.dumps(asdict(manifest), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest

    def restore(
        self,
        *,
        source: str | Path,
        sqlite_destinations: dict[str, str | Path],
    ) -> BackupManifest:
        root = Path(source)
        manifest = self._load_manifest(root)
        self._verify_manifest(root, manifest)

        for entry in manifest.files:
            path = root / entry.filename
            if entry.kind == "qdrant_collection":
                self._qdrant.restore_uploaded(
                    collection=entry.source,
                    snapshot=path,
                    checksum=entry.sha256,
                )
            elif entry.kind == "sqlite":
                destination = sqlite_destinations.get(entry.source)
                if destination is None:
                    raise ValueError(f"missing SQLite restore destination: {entry.source}")
                self._restore_sqlite(path, Path(destination))
            else:
                raise ValueError(f"unsupported backup file kind: {entry.kind}")
        return manifest

    @staticmethod
    def _backup_sqlite(source: Path, target: Path) -> None:
        if not source.is_file():
            raise FileNotFoundError(f"SQLite backup source is missing: {source}")
        with sqlite3.connect(source) as source_db, sqlite3.connect(target) as target_db:
            source_db.backup(target_db)

    @staticmethod
    def _restore_sqlite(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(source) as source_db, sqlite3.connect(target) as target_db:
            source_db.backup(target_db)

    @staticmethod
    def _file_entry(kind: str, source: str, path: Path) -> BackupFile:
        data = path.read_bytes()
        return BackupFile(
            kind=kind,
            source=source,
            filename=path.name,
            sha256=hashlib.sha256(data).hexdigest(),
            size=len(data),
        )

    @staticmethod
    def _load_manifest(root: Path) -> BackupManifest:
        raw = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if raw.get("format_version") != 1:
            raise ValueError("unsupported backup format_version")
        return BackupManifest(
            format_version=1,
            created_at=str(raw["created_at"]),
            files=[BackupFile(**item) for item in raw["files"]],
        )

    @staticmethod
    def _verify_manifest(root: Path, manifest: BackupManifest) -> None:
        for entry in manifest.files:
            path = root / entry.filename
            if not path.is_file():
                raise ValueError(f"backup file missing: {entry.filename}")
            data = path.read_bytes()
            if len(data) != entry.size:
                raise ValueError(f"backup file size mismatch: {entry.filename}")
            if hashlib.sha256(data).hexdigest() != entry.sha256:
                raise ValueError(f"backup checksum mismatch: {entry.filename}")
