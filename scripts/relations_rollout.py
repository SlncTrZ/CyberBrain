# SPDX-License-Identifier: MPL-2.0
"""Operator-only relation census/checkpoint/backfill; never called at normal startup."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from cyberbrain.backup.service import QdrantSnapshotClient
from cyberbrain.core.errors import ConfigurationError
from cyberbrain.core.settings import Settings
from cyberbrain.relations.maintenance import RelationMaintenance
from cyberbrain.relations.recall import RelationRecallRequest, RelationRecallService
from cyberbrain.relations.storage import RelationIndex
from cyberbrain.relations.traversal import RelationTraversal
from cyberbrain.storage.qdrant import QdrantRepository
from cyberbrain.tenancy import DeploymentMode
from cyberbrain.tenancy.durable import bind_job_authority


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["census", "checkpoint", "apply", "canary"])
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--expected-source-hash")
    parser.add_argument("--writers-quiesced", action="store_true")
    parser.add_argument("--seed-id", action="append", default=[])
    parser.add_argument("--max-records", type=int, default=50000)
    args = parser.parse_args()
    settings = Settings()
    settings.validate_runtime()
    if settings.deployment_mode != DeploymentMode.SINGLE_OWNER:
        raise ConfigurationError(
            "operator rollout requires explicit partition tooling outside single_owner"
        )
    repository = QdrantRepository(base_url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    if settings.knowledge_collection == settings.episodic_collection or any(
        repository.collection_info(name) is None
        for name in (settings.knowledge_collection, settings.episodic_collection)
    ):
        raise ConfigurationError("rollout requires both existing canonical collections")
    index = RelationIndex(repository, settings.knowledge_collection, settings.episodic_collection)
    maintenance = RelationMaintenance(index, max_records=args.max_records)
    with bind_job_authority(None):
        if args.operation == "census":
            result = asdict(maintenance.census())
        elif args.operation == "checkpoint":
            if args.checkpoint is None:
                parser.error("--checkpoint is required")
            census = maintenance.checkpoint(
                destination=args.checkpoint,
                snapshots=QdrantSnapshotClient(
                    base_url=settings.qdrant_url, api_key=settings.qdrant_api_key
                ),
                writers_quiesced=args.writers_quiesced,
            )
            result = asdict(census)
        elif args.operation == "apply":
            if args.checkpoint is None or not args.expected_source_hash:
                parser.error("--checkpoint and --expected-source-hash are required")
            result = asdict(
                maintenance.apply(
                    checkpoint=args.checkpoint,
                    expected_source_hash=args.expected_source_hash,
                    writers_quiesced=args.writers_quiesced,
                )
            )
        else:
            index.verify_indexes()
            recalled = RelationRecallService(RelationTraversal(index)).recall(
                RelationRecallRequest(seed_ids=tuple(args.seed_id))
            )
            result = {
                key: recalled[key]
                for key in (
                    "returned_path_count",
                    "returned_record_count",
                    "storage_calls",
                    "truncated",
                    "truncation_reasons",
                    "estimated_tokens",
                    "mode",
                )
            }
        print(json.dumps(result, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
