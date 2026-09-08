# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json

from benchmarks.retrieval.benchmark_real_snapshot import literal_heavy_query, run


def test_literal_heavy_query_detects_fingerprints_but_not_plain_semantics() -> None:
    assert literal_heavy_query("deploy commit c5a8ed9") is True
    assert literal_heavy_query("qwen3:0.6b parameters 5/5") is True
    assert literal_heavy_query("package version 0.40.0") is True
    assert literal_heavy_query("why did the provider remain out of sync") is False


def test_real_snapshot_runner_routes_literal_queries_without_scope_leak(tmp_path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    cases = tmp_path / "cases.json"
    semantic = tmp_path / "semantic.json"

    rows = [
        {
            "id": "target",
            "content": "release commit abc1234 exact fingerprint",
            "summary": "target",
            "project": "p",
            "topic": "release",
            "entity_name": "target",
            "status": "active",
        },
        {
            "id": "outside",
            "content": "release commit abc1234 exact fingerprint",
            "summary": "outside",
            "project": None,
            "topic": "release",
            "entity_name": "outside",
            "status": "active",
        },
    ]
    corpus.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    cases.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "c1",
                        "category": "exact_identifier",
                        "query": "release commit abc1234",
                        "expected_ids": ["target"],
                        "forbidden_ids": ["outside"],
                        "project": "p",
                        "status": "active",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    semantic.write_text(
        json.dumps(
            {
                "source": "test",
                "thresholds": [0.55],
                "cases": {"c1": {"ids": ["target"], "latency_ms": 10.0}},
            }
        ),
        encoding="utf-8",
    )

    report = run(corpus_path=corpus, cases_path=cases, semantic_path=semantic, k=5)

    assert report["reports"]["literal_router"]["recall_at_k"] == 1.0
    assert report["reports"]["literal_router"]["contamination_rate"] == 0.0
    assert report["per_case"][0]["route"] == "lexical"
    assert report["per_case"][0]["lexical_top_k"] == ["target"]
