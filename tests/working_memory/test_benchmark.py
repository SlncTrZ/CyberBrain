# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from benchmarks.working_memory.benchmark import run


def test_controlled_benchmark_meets_m5_source_acceptance() -> None:
    report = run()

    assert report["task_count"] == 4
    assert report["step_count"] == 16
    assert report["accepted"] is True
    assert report["changes_runtime_behavior"] is False
    assert report["working_memory"]["required_context_coverage"] >= 0.95
    assert (
        report["working_memory"]["required_context_coverage"]
        > report["baseline"]["required_context_coverage"]
    )
    assert report["working_memory"]["memory_tokens"] <= report["baseline"]["memory_tokens"]
    assert report["working_memory"]["repeated_context_injections"] == 0
    assert report["working_memory"]["stale_context_contamination"] == 0
    assert report["working_memory"]["cross_task_leakage"] == 0
    assert report["working_memory"]["exact_fetch_count"] <= report["baseline"]["exact_fetch_count"]
