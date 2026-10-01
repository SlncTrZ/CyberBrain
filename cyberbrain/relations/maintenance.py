# SPDX-License-Identifier: MPL-2.0
"""Explicit quiesced projection rollout with census and verified snapshot checkpoint."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from cyberbrain.backup.service import BackupService, QdrantSnapshotClient
from cyberbrain.core.errors import ConfigurationError, ConflictError
from cyberbrain.tenancy import current_authority
from cyberbrain.tenancy.enforcement import TenancyOperation
from cyberbrain.tenancy.runtime import enforce_operation

from .admission import _canonical_payload, require_review_authority
from .index import INDEX_KEY, project_relations, verify_projection
from .models import bundle_from_extensions, canonical_json, fingerprint
from .storage import RelationIndex


@dataclass(frozen=True)
class RelationCensus:
    source_hash: str
    records: int
    missing: int
    eligible: int
    assertions: int
    pages: int


class RelationMaintenance:
    def __init__(
        self, index: RelationIndex, *, max_records: int = 50000, max_payload_bytes: int = 67108864
    ):
        if type(max_records) is not int or not 1 <= max_records <= 50000:
            raise ValueError("maintenance record limit must be between 1 and 50000")
        if type(max_payload_bytes) is not int or not 1024 <= max_payload_bytes <= 67108864:
            raise ValueError("maintenance payload limit must be between 1024 and 67108864")
        self.index = index
        self.max_records = max_records
        self.max_payload_bytes = max_payload_bytes

    def _scan(self):
        require_review_authority()
        conditions = self.index.conditions()
        query = {
            "must": [
                *conditions,
                {"key": "record_type", "match": {"value": "knowledge"}},
                {"key": "record_class", "match": {"value": "knowledge"}},
            ]
        }
        records = []
        offset = None
        offsets = set()
        pages = 0
        size = 0
        while True:
            points, continuation = self.index.repository.scroll_page(
                self.index.knowledge_collection, qdrant_filter=query, limit=256, offset=offset
            )
            pages += 1
            for point in points:
                payload = _canonical_payload(point, record_type="knowledge", point_id=point["id"])
                projection = project_relations(payload)
                extensions = dict(payload["extensions"])
                if INDEX_KEY in extensions:
                    # Never overwrite a legacy namespace collision or unexplained corruption.
                    verify_projection(payload)
                raw = dict(point["payload"])
                raw["extensions"] = dict(raw.get("extensions") or {})
                raw["extensions"].pop(INDEX_KEY, None)
                size += len(canonical_json(raw).encode("utf-8"))
                if len(records) >= self.max_records or size > self.max_payload_bytes:
                    raise ConfigurationError("relation census capacity exceeded")
                records.append((str(point["id"]), raw, extensions, projection))
            if continuation is None:
                break
            marker = str(continuation)
            if not points or marker in offsets:
                raise ConfigurationError("relation census continuation is inconsistent")
            offsets.add(marker)
            offset = continuation
        records.sort(key=lambda record: record[0])
        if len({record[0] for record in records}) != len(records):
            raise ConflictError("relation census contains duplicate point IDs")
        scope = current_authority().grant.scope.as_dict()
        source_hash = fingerprint(
            {
                "collection": self.index.knowledge_collection,
                "scope": scope,
                "records": [(point_id, payload) for point_id, payload, _, _ in records],
            }
        )
        census = RelationCensus(
            source_hash=source_hash,
            records=len(records),
            missing=sum(INDEX_KEY not in extensions for _, _, extensions, _ in records),
            eligible=sum(projection["eligible"] for _, _, _, projection in records),
            assertions=sum(
                len(bundle_from_extensions(extensions).edges) for _, _, extensions, _ in records
            ),
            pages=pages,
        )
        return census, records

    def census(self) -> RelationCensus:
        return self._scan()[0]

    @staticmethod
    def _quiesced(writers_quiesced: bool) -> None:
        if writers_quiesced is not True:
            raise ConfigurationError("relation rollout requires quiesced canonical writers")

    def checkpoint(
        self,
        *,
        destination: Path,
        snapshots: QdrantSnapshotClient,
        writers_quiesced: bool,
        sqlite_files: dict | None = None,
    ) -> RelationCensus:
        self._quiesced(writers_quiesced)
        require_review_authority()
        enforce_operation(TenancyOperation.KNOWLEDGE_WRITE)
        before = self.census()
        service = BackupService(
            qdrant=snapshots,
            collections=[self.index.knowledge_collection, self.index.episodic_collection],
        )
        previous_umask = os.umask(0o077)
        try:
            service.create(destination=destination, sqlite_files=sqlite_files or {})
            manifest = service._load_manifest(destination)
            service._verify_manifest(destination, manifest)
            after = self.census()
            if before.source_hash != after.source_hash:
                raise ConflictError("canonical data changed while capturing relation checkpoint")
            (destination / "relation-census.json").write_text(
                canonical_json(
                    {
                        "schema_version": 1,
                        "source_hash": before.source_hash,
                        "knowledge_collection": self.index.knowledge_collection,
                        "episodic_collection": self.index.episodic_collection,
                        "manifest_hash": fingerprint(
                            json.loads((destination / "manifest.json").read_text())
                        ),
                    }
                )
            )
        finally:
            os.umask(previous_umask)
        return before

    def apply(
        self, *, checkpoint: Path, expected_source_hash: str, writers_quiesced: bool
    ) -> RelationCensus:
        self._quiesced(writers_quiesced)
        require_review_authority()
        enforce_operation(TenancyOperation.KNOWLEDGE_WRITE)
        metadata = json.loads((checkpoint / "relation-census.json").read_text())
        if (
            type(metadata.get("schema_version")) is not int
            or metadata["schema_version"] != 1
            or metadata.get("source_hash") != expected_source_hash
            or metadata.get("knowledge_collection") != self.index.knowledge_collection
            or metadata.get("episodic_collection") != self.index.episodic_collection
            or metadata.get("manifest_hash")
            != fingerprint(json.loads((checkpoint / "manifest.json").read_text()))
        ):
            raise ConfigurationError("relation checkpoint does not match rollout source")
        manifest = BackupService._load_manifest(checkpoint)
        BackupService._verify_manifest(checkpoint, manifest)
        collections = {file.source for file in manifest.files if file.kind == "qdrant_collection"}
        if collections != {self.index.knowledge_collection, self.index.episodic_collection}:
            raise ConfigurationError("relation checkpoint must cover both canonical collections")
        before, records = self._scan()
        if before.source_hash != expected_source_hash:
            raise ConflictError("canonical data changed; capture a fresh relation checkpoint")
        self.index.prepare_indexes()
        for point_id, _, extensions, projection in records:
            if INDEX_KEY in extensions:
                continue
            extensions[INDEX_KEY] = projection
            self.index.repository.set_payload(
                self.index.knowledge_collection,
                point_id=UUID(point_id),
                payload={"extensions": extensions},
            )
        after = self.census()
        if (
            after.source_hash != before.source_hash
            or after.records != before.records
            or after.missing
        ):
            raise ConflictError("relation projection verification failed")
        return after
