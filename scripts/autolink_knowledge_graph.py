# SPDX-License-Identifier: MPL-2.0
"""Automated Knowledge Graph Entity Linker & Edge Builder.

Scans existing knowledge records, discovers semantic relations within the same tenant scope,
validates through admit_relations, and populates _relation_index with real graph edges.
Updated: 2026-10-24 14:00
"""

from __future__ import annotations

import argparse
import inspect
from datetime import UTC, datetime
from uuid import UUID

from cyberbrain.core.runtime import build_runtime
from cyberbrain.core.settings import Settings
from cyberbrain.embedding.base import EmbeddingProvider
from cyberbrain.relations.admission import (
    _canonical_payload,
    _partition_conditions,
    admit_relations,
)
from cyberbrain.relations.index import INDEX_KEY, project_relations
from cyberbrain.relations.models import (
    EntityRef,
    EvidenceRef,
    RelationBundle,
    RelationEdge,
    RelationKind,
    RelationStatus,
    bundle_from_extensions,
)
from cyberbrain.storage.qdrant import QdrantRepository
from cyberbrain.tenancy.durable import bind_job_authority


def autolink_knowledge_graph(
    *,
    repository: QdrantRepository,
    collection: str,
    embedding: EmbeddingProvider | None = None,
    score_threshold: float = 0.78,
    limit_per_record: int = 2,
    max_records: int = 5000,
    status: str = "proposed",
    dry_run: bool = False,
) -> dict[str, int]:
    edge_status = RelationStatus(status)
    query = {
        "must": [
            {"key": "record_type", "match": {"value": "knowledge"}},
            {"key": "record_class", "match": {"value": "knowledge"}},
            {"key": "status", "match": {"value": "active"}},
        ]
    }

    records_scanned = 0
    records_updated = 0
    edges_created = 0
    offset = None
    now = datetime.now(UTC)

    print(
        f"Scanning up to {max_records} active records in '{collection}' "
        f"(status={edge_status.value}, dry_run={dry_run})..."
    )

    while records_scanned < max_records:
        fetch_limit = min(100, max_records - records_scanned)
        scroll_kwargs = (
            {"with_vector": True}
            if "with_vector" in inspect.signature(repository.scroll_page).parameters
            else {}
        )
        points, continuation = repository.scroll_page(
            collection,
            qdrant_filter=query,
            limit=fetch_limit,
            offset=offset,
            **scroll_kwargs,
        )
        if not points:
            break

        for point in points:
            records_scanned += 1
            point_id = UUID(str(point["id"]))

            try:
                canonical = _canonical_payload(point, record_type="knowledge", point_id=point_id)
                source_ref = EntityRef.from_payload(canonical)
            except Exception:
                continue

            vector = point.get("vector")
            if not vector or not isinstance(vector, list):
                if embedding is None:
                    continue
                lookup_text = (
                    f"{canonical['topic']} {canonical['entity_name']} "
                    f"{canonical.get('summary') or canonical['content'][:150]}"
                ).strip()
                try:
                    vector = embedding.embed(lookup_text)
                except Exception as exc:
                    print(f"Embedding failed for {source_ref.key}: {exc}")
                    continue

            # Tenancy-isolated search filter: strictly within source_ref's partition
            partition_conds = _partition_conditions(source_ref.scope, include_session=True)
            search_filter = {
                "must": [
                    *partition_conds,
                    {"key": "record_type", "match": {"value": "knowledge"}},
                    {"key": "record_class", "match": {"value": "knowledge"}},
                    {"key": "status", "match": {"value": "active"}},
                    {"key": "ordinary_recall", "match": {"value": True}},
                ]
            }

            matches = repository.search(
                collection,
                vector=vector,
                limit=limit_per_record + 2,
                score_threshold=score_threshold,
                qdrant_filter=search_filter,
            )

            existing_bundle = bundle_from_extensions(canonical.get("extensions") or {})
            existing_targets = {edge.target.key for edge in existing_bundle.edges}
            new_edges = []
            upgraded_edges = 0
            for edge in existing_bundle.edges:
                is_upgradable = (
                    edge_status == RelationStatus.ACCEPTED
                    and edge.status == RelationStatus.PROPOSED
                )
                if is_upgradable:
                    new_edges.append(
                        edge.model_copy(
                            update={"status": RelationStatus.ACCEPTED, "valid_from": now}
                        )
                    )
                    upgraded_edges += 1
                else:
                    new_edges.append(edge)
            added_this_record = upgraded_edges

            for match in matches:
                if str(match["id"]) == str(point_id):
                    continue
                match_payload = match.get("payload") or {}
                try:
                    target_ref = EntityRef.from_payload(match_payload)
                except Exception:
                    continue

                if target_ref.key == source_ref.key or target_ref.key in existing_targets:
                    continue

                target_id = UUID(str(match["id"]))
                edge = RelationEdge(
                    kind=RelationKind.SUPPORTS,
                    source=source_ref,
                    target=target_ref,
                    target_record_id=target_id,
                    evidence=(EvidenceRef(record_type="knowledge", id=point_id),),
                    status=edge_status,
                    review_note="Automated semantic similarity edge",
                    valid_from=now,
                )
                new_edges.append(edge)
                existing_targets.add(target_ref.key)
                added_this_record += 1
                edges_created += 1

                if added_this_record >= limit_per_record:
                    break

            admitted_edges = []
            for edge in new_edges:
                test_bundle = RelationBundle(schema_version=1, edges=(edge,))
                try:
                    admit_relations(
                        raw=test_bundle.model_dump(mode="json"),
                        source=source_ref,
                        repository=repository,
                        knowledge_collection=collection,
                        episodic_collection=None,
                    )
                    admitted_edges.append(edge)
                except Exception:
                    continue

            if admitted_edges:
                admitted_bundle = RelationBundle(schema_version=1, edges=tuple(admitted_edges))
                extensions = dict(canonical.get("extensions") or {})
                extensions["relations"] = admitted_bundle.model_dump(mode="json")
                canonical["extensions"] = extensions
                projection = project_relations(canonical)
                extensions[INDEX_KEY] = projection

                if dry_run:
                    print(
                        f"[DRY-RUN] Would link: {source_ref.key} -> "
                        f"{len(admitted_edges)} valid targets"
                    )
                else:
                    repository.set_payload(
                        collection,
                        point_id=point_id,
                        payload={"extensions": extensions},
                    )
                    records_updated += 1

        print(
            f"Progress: scanned {records_scanned}/{max_records} | "
            f"updated {records_updated} records | edges created: {edges_created}"
        )

        if continuation is None:
            break
        offset = continuation

    result = {
        "records_scanned": records_scanned,
        "records_updated": records_updated,
        "edges_created": edges_created,
        "dry_run": int(dry_run),
    }
    print(f"\nKnowledge Graph Autolink finished: {result}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-url", default=None)
    parser.add_argument("--embedding-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--score-threshold", type=float, default=0.78)
    parser.add_argument("--limit-per-record", type=int, default=2)
    parser.add_argument("--max-records", type=int, default=5000)
    parser.add_argument(
        "--status",
        choices=["proposed", "accepted"],
        default="proposed",
        help="Status for created edges (default: proposed)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = Settings()
    if args.qdrant_url:
        settings.qdrant_url = args.qdrant_url
    if args.embedding_url:
        settings.embedding_url = args.embedding_url
    if args.api_key:
        settings.qdrant_api_key = args.api_key

    services = build_runtime(settings)
    repository = QdrantRepository(base_url=settings.qdrant_url, api_key=settings.qdrant_api_key)

    with bind_job_authority(None):
        autolink_knowledge_graph(
            repository=repository,
            collection=settings.knowledge_collection,
            embedding=services.embedding,
            score_threshold=args.score_threshold,
            limit_per_record=args.limit_per_record,
            max_records=args.max_records,
            status=args.status,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
