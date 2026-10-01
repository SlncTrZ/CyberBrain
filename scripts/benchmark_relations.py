# SPDX-License-Identifier: MPL-2.0
"""Run only against a new empty loopback Qdrant. Results contain synthetic metrics."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

import httpx

from cyberbrain.relations.benchmark import RelationBenchmark, RelationBenchmarkCase
from cyberbrain.relations.index import INDEX_KEY, project_relations
from cyberbrain.relations.models import (
    EntityRef,
    EvidenceRef,
    RelationBundle,
    RelationEdge,
    fingerprint,
)
from cyberbrain.relations.recall import RelationRecallRequest, RelationRecallService
from cyberbrain.relations.storage import RelationIndex
from cyberbrain.relations.traversal import RelationTraversal, TraversalPolicy
from cyberbrain.retrieval.benchmark import BenchmarkCase
from cyberbrain.retrieval.models import RetrievalIntent
from cyberbrain.schemas.models import KnowledgeRecord, KnowledgeStatus
from cyberbrain.storage.qdrant import QdrantRepository
from cyberbrain.tenancy import (
    DeploymentMode,
    IdentityScope,
    OperationClass,
    authority_for_authenticated_scope,
    bind_authority,
)


class InstrumentedRepository(QdrantRepository):
    request_count = 0

    def _send(self, *args, **kwargs):
        self.request_count += 1
        return super()._send(*args, **kwargs)


class FixtureEmbedding:
    dimension = 3
    version = "deterministic-fixture@v1"
    calls = 0

    def embed(self, query):
        self.calls += 1
        return [1.0, 0.0, 0.0]


def record(name, *, project="comparison", tenant="bench", content=None, version=1, year=2020):
    return KnowledgeRecord(
        id=uuid5(
            NAMESPACE_URL, f"cyberbrain-relation-benchmark/{tenant}/{project}/{name}/{version}"
        ),
        content=content or name,
        content_hash=hashlib.sha256((content or name).encode()).hexdigest(),
        domain="qa",
        topic="relations",
        entity_type="component",
        entity_name=name,
        tenant=tenant,
        user="fixture",
        agent="fixture",
        project=project,
        version=version,
        created_at=datetime(year, 1, 1, tzinfo=UTC),
        updated_at=datetime(year, 1, 1, tzinfo=UTC),
    )


def payload(item):
    value = item.model_dump(mode="json")
    value["extensions"][INDEX_KEY] = project_relations(value)
    return value


def edge(source, target):
    return RelationEdge(
        kind="depends_on",
        source=EntityRef.from_payload(source.model_dump(mode="json")),
        target=EntityRef.from_payload(target.model_dump(mode="json")),
        target_record_id=target.id,
        evidence=(EvidenceRef(record_type="knowledge", id=target.id),),
        status="accepted",
        review_note="Curated synthetic structural assertion.",
        valid_from=datetime(2020, 1, 1, tzinfo=UTC),
    )


def caller(project="comparison"):
    return authority_for_authenticated_scope(
        DeploymentMode.MULTI_USER,
        scope=IdentityScope.from_values(
            tenant="bench", user="fixture", agent="fixture", project=project
        ),
        operations=frozenset(OperationClass),
    )


def write_batch(repository, items):
    for start in range(0, len(items), 128):
        repository._request(
            "PUT",
            "/collections/cyberbrain_knowledge/points?wait=true",
            json={"points": items[start : start + 128]},
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--corpus-size", type=int, default=1000)
    args = parser.parse_args()
    parsed = urlsplit(args.qdrant_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        parser.error("benchmark requires an empty loopback-only Qdrant")
    if not 0 <= args.corpus_size <= 10000:
        parser.error("corpus-size must be between 0 and 10000")
    repository = InstrumentedRepository(base_url=args.qdrant_url)
    collections = httpx.get(args.qdrant_url + "/collections").json()["result"]["collections"]
    if collections:
        parser.error("benchmark refuses a non-empty Qdrant instance")
    for name in ("cyberbrain_knowledge", "cyberbrain_episodic"):
        repository.ensure_collection(name, vector_size=3)
    embedding = FixtureEmbedding()
    records = {
        "a": record("a", content="API contract entrypoint"),
        "b": record("b", content="Storage durability subsystem"),
        "c": record("c", content="Transport fanout subsystem"),
        "d": record("d", content="Commit outcome pipeline"),
    }
    for name, targets in {"a": ["b", "c"], "b": ["d"], "c": ["d"], "d": []}.items():
        records[name].extensions["relations"] = RelationBundle(
            schema_version=1,
            edges=tuple(edge(records[name], records[target]) for target in targets),
        ).model_dump(mode="json")
    successor = record("b", content="Changed storage interface", version=2, year=2022)
    successor.supersedes_id = records["b"].id
    records["b"].status = KnowledgeStatus.SUPERSEDED
    records["b"].superseded_by_id = successor.id
    vectors = {"a": [1, 0, 0], "b": [0.3, 0.95, 0], "c": [0.3, 0.95, 0], "d": [-1, 0, 0]}
    points = [
        {"id": str(item.id), "vector": vectors[name], "payload": payload(item)}
        for name, item in records.items()
    ]
    points.append({"id": str(successor.id), "vector": [0.6, 0.8, 0], "payload": payload(successor)})
    foreign = record("foreign", tenant="foreign", content="API contract entrypoint")
    points.append({"id": str(foreign.id), "vector": [1, 0, 0], "payload": payload(foreign)})
    for number in range(args.corpus_size):
        item = record(f"filler-{number}", content=f"Unrelated inventory ticket {number}")
        points.append({"id": str(item.id), "vector": [-1, 0, 0], "payload": payload(item)})
    write_batch(repository, points)
    index = RelationIndex(repository, "cyberbrain_knowledge", "cyberbrain_episodic")
    with bind_authority(caller()):
        index.prepare_indexes()
    service = RelationRecallService(RelationTraversal(index))
    ids = {name: str(item.id) for name, item in records.items()}
    definitions = [
        (
            "current-out",
            "API contract dependencies",
            "a",
            "out",
            2,
            None,
            ("c", "d"),
            (("a", "c"), ("a", "c", "d")),
        ),
        (
            "current-reverse",
            "API contract upstream",
            "d",
            "in",
            2,
            None,
            ("c", "a"),
            (("d", "c"), ("d", "c", "a")),
        ),
        ("direct-out", "API contract dependencies", "a", "out", 1, None, ("c",), (("a", "c"),)),
        ("lexical-control", "Transport fanout", "a", "out", 1, None, ("c",), (("a", "c"),)),
        (
            "historical-out",
            "API contract dependencies",
            "a",
            "out",
            2,
            datetime(2021, 1, 1, tzinfo=UTC),
            ("b", "c", "d"),
            (("a", "b"), ("a", "c"), ("a", "b", "d"), ("a", "c", "d")),
        ),
    ]
    runner = RelationBenchmark(
        repository=repository,
        embedding=embedding,
        collection="cyberbrain_knowledge",
        service=service,
        iterations=args.iterations,
    )
    cases = []
    with bind_authority(caller()):
        for name, query, seed, direction, depth, at, targets, paths in definitions:
            case = RelationBenchmarkCase(
                baseline=BenchmarkCase(
                    case_id=name,
                    query=query,
                    intent=RetrievalIntent.CURRENT_FACT,
                    expected_ids=tuple(ids[target] for target in targets),
                    forbidden_ids=(str(foreign.id), str(successor.id)),
                    project="comparison",
                    not_after=at,
                ),
                request=RelationRecallRequest(
                    seed_ids=(records[seed].id,),
                    policy=TraversalPolicy(direction=direction, depth=depth, as_of=at),
                    context_tokens=4096,
                    record_tokens=256,
                ),
                expected_paths=frozenset(tuple(ids[node] for node in path) for path in paths),
            )
            cases.append(runner.run_case(case))
    scalability = []
    for fanout in (1, 8, 64, 256):
        project = f"fanout-{fanout}"
        leaf = record("leaf", project=project)
        entries = [{"id": str(leaf.id), "vector": [1, 0, 0], "payload": payload(leaf)}]
        for number in range(fanout):
            source = record(f"owner-{number}", project=project)
            source.extensions["relations"] = RelationBundle(
                schema_version=1, edges=(edge(source, leaf),)
            ).model_dump(mode="json")
            entries.append({"id": str(source.id), "vector": [0, 1, 0], "payload": payload(source)})
        write_batch(repository, entries)
        with bind_authority(caller(project)):
            repository.request_count = 0
            output = service.recall(
                RelationRecallRequest(
                    seed_ids=(leaf.id,),
                    policy=TraversalPolicy(
                        depth=1, direction="in", max_nodes=128, max_edges=256, max_paths=128
                    ),
                    context_tokens=16384,
                    record_tokens=32,
                )
            )
        scalability.append(
            {
                "fanout": fanout,
                "validated_edges": output["edge_count"],
                "returned_paths": output["returned_path_count"],
                "storage_calls": repository.request_count,
                "context_tokens": output["estimated_tokens"],
                "truncation_reasons": output["truncation_reasons"],
            }
        )
    source = Path(__file__).resolve().parents[1]
    source_hash = fingerprint(
        {
            str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((source / "cyberbrain").rglob("*.py"))
        }
    )
    version = httpx.get(args.qdrant_url + "/").json().get("version")
    report = {
        "schema_version": 1,
        "measured_at": datetime.now(UTC).isoformat(),
        "source_tree_hash": source_hash,
        "fixture_hash": fingerprint(points),
        "backend": "real isolated Qdrant",
        "qdrant_version": version,
        "embedding": "deterministic synthetic 3D; no trained embedding quality claim",
        "transport": "runtime-default pooled HTTP client; setup and one warm-up excluded",
        "scope": "known-seed structural retrieval; no query-to-seed resolution tested",
        "longitudinal_live_evidence": "outside this source gate",
        "canonical_collections": 2,
        "comparison_corpus_points": len(points),
        "equal_context_budget": 4096,
        "equal_record_text_budget": 256,
        "k": runner.k,
        "cases": cases,
        "fanout": scalability,
        "limitations": [
            "Curated synthetic distances and labels; does not estimate general retrieval accuracy.",
            "Historical ordinary-search baselines are unsupported, not scored as zero.",
            "No competitor implementations, semantic entailment, or long-term utility measured.",
            "Depth truncation is conservative even when paths match the finite gold set.",
        ],
    }
    assert all(
        case["modes"]["relations"]["path_precision"] == 1
        and case["modes"]["relations"]["path_recall"] == 1
        for case in cases
    )
    assert "candidate_capacity" in scalability[-1]["truncation_reasons"]
    assert scalability[-1]["returned_paths"] == 0
    assert all(row["storage_calls"] <= 8 and row["context_tokens"] <= 16384 for row in scalability)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "cases": len(cases),
                "fanout_cases": len(scalability),
                "source_tree_hash": source_hash,
            }
        )
    )


if __name__ == "__main__":
    main()
