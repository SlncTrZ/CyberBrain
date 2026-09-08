# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from time import perf_counter
from typing import Any

from cyberbrain.retrieval.engine import HybridRetrievalEngine
from cyberbrain.retrieval.literal import literal_heavy_query
from cyberbrain.retrieval.models import RetrievalHit
from cyberbrain.retrieval.signals import ScopeTemporalSignals


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"expected JSON object row: {path}")
        rows.append(value)
    return rows


def _compact_text(row: dict[str, Any]) -> str:
    summary = str(row.get("summary") or "").strip()
    if summary:
        return summary
    return str(row.get("content") or "")[:1200]


def _rank(ids: list[str], relevant: set[str]) -> int | None:
    return next(
        (rank for rank, record_id in enumerate(ids, start=1) if record_id in relevant),
        None,
    )


def _classify_change(
    ranks: dict[str, int | None],
    *,
    target: str,
    accumulator: dict[str, int],
    k: int,
) -> None:
    vector_rank = ranks["vector"]
    target_rank = ranks[target]
    vector_in_k = vector_rank is not None and vector_rank <= k
    target_in_k = target_rank is not None and target_rank <= k
    if not vector_in_k and target_in_k:
        accumulator["rescued_at_k"] += 1
        accumulator["improved"] += 1
    elif vector_rank is not None and target_rank is not None and target_rank < vector_rank:
        accumulator["improved"] += 1
    elif vector_rank is not None and (target_rank is None or target_rank > vector_rank):
        accumulator["regressed"] += 1
    else:
        accumulator["same"] += 1


def _metrics(
    ids: list[str],
    case: dict[str, Any],
    *,
    compact_by_id: dict[str, str],
    k: int,
) -> dict[str, float]:
    selected = ids[:k]
    expected = set(case["expected_ids"])
    relevant = expected | set(case.get("acceptable_ids", []))
    forbidden = set(case.get("forbidden_ids", []))
    recall = sum(record_id in expected for record_id in selected) / len(expected)
    reciprocal_rank = next(
        (1.0 / rank for rank, record_id in enumerate(selected, start=1) if record_id in relevant),
        0.0,
    )
    contamination = (
        sum(record_id in forbidden for record_id in selected) / len(selected) if selected else 0.0
    )
    token_estimate = sum(
        (len(compact_by_id.get(record_id, "")) + 3) // 4 for record_id in selected
    )
    return {
        "recall_at_k": recall,
        "mrr_at_k": reciprocal_rank,
        "contamination_rate": contamination,
        "returned_token_estimate": float(token_estimate),
    }


def _aggregate(rows: list[dict[str, float]]) -> dict[str, float]:
    return {
        "recall_at_k": round(statistics.mean(row["recall_at_k"] for row in rows), 6),
        "mrr_at_k": round(statistics.mean(row["mrr_at_k"] for row in rows), 6),
        "contamination_rate": round(
            statistics.mean(row["contamination_rate"] for row in rows), 6
        ),
        "mean_returned_token_estimate": round(
            statistics.mean(row["returned_token_estimate"] for row in rows), 3
        ),
    }


def run(
    *,
    corpus_path: Path,
    cases_path: Path,
    semantic_path: Path,
    k: int = 5,
) -> dict[str, Any]:
    if k < 1:
        raise ValueError("k must be positive")

    corpus = _load_jsonl(corpus_path)
    cases = _load_json(cases_path).get("cases")
    semantic_root = _load_json(semantic_path)
    semantic = semantic_root.get("cases")
    if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
        raise ValueError("case manifest must contain a cases list")
    if not isinstance(semantic, dict):
        raise ValueError("semantic snapshot must contain a cases object")

    hits: list[RetrievalHit] = []
    hit_by_id: dict[str, RetrievalHit] = {}
    compact_by_id: dict[str, str] = {}
    for row in corpus:
        record_id = str(row.get("id") or "").strip()
        if not record_id:
            raise ValueError("corpus row is missing id")
        hit = RetrievalHit(
            id=record_id,
            text=str(row.get("content") or ""),
            project=row.get("project"),
            topic=row.get("topic"),
            entity_name=row.get("entity_name"),
            status=row.get("status"),
        )
        hits.append(hit)
        hit_by_id[record_id] = hit
        compact_by_id[record_id] = _compact_text(row)

    engine = HybridRetrievalEngine(hits)
    signals = ScopeTemporalSignals()
    channel_metrics: dict[str, list[dict[str, float]]] = {
        "vector": [],
        "lexical": [],
        "hybrid": [],
        "literal_router": [],
    }
    by_category: dict[tuple[str, str], list[dict[str, float]]] = {}
    per_case: list[dict[str, Any]] = []
    local_overhead_ms: list[float] = []
    vector_latencies_ms: list[float] = []
    global_changes = {"improved": 0, "regressed": 0, "same": 0, "rescued_at_k": 0}
    router_changes = {"improved": 0, "regressed": 0, "same": 0, "rescued_at_k": 0}

    for case in cases:
        case_id = str(case["case_id"])
        semantic_case = semantic.get(case_id)
        if not isinstance(semantic_case, dict):
            raise ValueError(f"semantic snapshot is missing case: {case_id}")
        semantic_ids = tuple(str(value) for value in semantic_case.get("ids", []))
        vector_latency = float(semantic_case.get("latency_ms", 0.0))
        vector_latencies_ms.append(vector_latency)

        started = perf_counter()
        result = engine.query(
            str(case["query"]),
            semantic_ranked_ids=semantic_ids,
            project=case.get("project"),
            topic=case.get("topic"),
            entity_name=case.get("entity_name"),
            status=case.get("status"),
        )
        local_overhead_ms.append((perf_counter() - started) * 1000)

        vector_ids = [row.id for row in result.semantic]
        lexical_ids: list[str] = []
        for row in result.lexical:
            hit = hit_by_id[row.id]
            allowed, _reasons = signals.contributions(
                hit,
                project=case.get("project"),
                topic=case.get("topic"),
                entity_name=case.get("entity_name"),
                status=case.get("status"),
            )
            if allowed:
                lexical_ids.append(row.id)
        hybrid_ids = [row.id for row in result.hybrid]
        route = "lexical" if literal_heavy_query(str(case["query"])) else "vector"
        routed_ids = lexical_ids if route == "lexical" else vector_ids

        relevant = set(case["expected_ids"]) | set(case.get("acceptable_ids", []))
        ranks = {
            "vector": _rank(vector_ids, relevant),
            "lexical": _rank(lexical_ids, relevant),
            "hybrid": _rank(hybrid_ids, relevant),
            "literal_router": _rank(routed_ids, relevant),
        }

        _classify_change(ranks, target="hybrid", accumulator=global_changes, k=k)
        _classify_change(ranks, target="literal_router", accumulator=router_changes, k=k)

        ids_by_channel = {
            "vector": vector_ids,
            "lexical": lexical_ids,
            "hybrid": hybrid_ids,
            "literal_router": routed_ids,
        }
        category = str(case.get("category") or "uncategorized")
        for channel, ids in ids_by_channel.items():
            metric = _metrics(ids, case, compact_by_id=compact_by_id, k=k)
            channel_metrics[channel].append(metric)
            by_category.setdefault((category, channel), []).append(metric)

        per_case.append(
            {
                "case_id": case_id,
                "category": category,
                "route": route,
                "ranks": ranks,
                "vector_top_k": vector_ids[:k],
                "lexical_top_k": lexical_ids[:k],
                "hybrid_top_k": hybrid_ids[:k],
                "literal_router_top_k": routed_ids[:k],
                "vector_latency_ms": vector_latency,
            }
        )

    categories = sorted({str(case.get("category") or "uncategorized") for case in cases})
    return {
        "case_count": len(cases),
        "k": k,
        "semantic_source": semantic_root.get("source"),
        "semantic_thresholds": semantic_root.get("thresholds"),
        "reports": {name: _aggregate(metrics) for name, metrics in channel_metrics.items()},
        "by_category": {
            category: {
                channel: _aggregate(by_category[(category, channel)])
                for channel in channel_metrics
            }
            for category in categories
        },
        "rank_changes_vs_vector": {
            "hybrid": global_changes,
            "literal_router": router_changes,
        },
        "latency": {
            "mean_vector_ms": round(statistics.mean(vector_latencies_ms), 3),
            "mean_local_hybrid_overhead_ms": round(statistics.mean(local_overhead_ms), 3),
            "p95_local_hybrid_overhead_ms": round(
                sorted(local_overhead_ms)[max(0, int(len(local_overhead_ms) * 0.95) - 1)], 3
            ),
        },
        "per_case": per_case,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark live vector rankings against local BM25/RRF"
    )
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--semantic", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    report = run(
        corpus_path=args.corpus,
        cases_path=args.cases,
        semantic_path=args.semantic,
        k=args.k,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
