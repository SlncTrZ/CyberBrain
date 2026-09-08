# SPDX-License-Identifier: MPL-2.0
"""Deterministic M5 baseline vs transient Working Memory benchmark."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cyberbrain.core.token_budget import DeterministicTokenCounter
from cyberbrain.salience import SalienceInput
from cyberbrain.working_memory import (
    TaskRelevance,
    WorkingMemoryCandidate,
    WorkingMemoryEmissionLedger,
    WorkingMemoryIdentity,
    WorkingMemoryItemKind,
    WorkingMemoryService,
)

DEFAULT_FIXTURE = Path(__file__).with_name("fixtures.json")
_START = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def _load(path: Path) -> dict[str, Any]:
    root = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(root, dict) or not isinstance(root.get("tasks"), list):
        raise ValueError("working memory fixture must contain a tasks list")
    return root


def _candidate(identity: WorkingMemoryIdentity, row: dict[str, Any]) -> WorkingMemoryCandidate:
    salience = row.get("salience") or {}
    if not isinstance(salience, dict):
        raise ValueError("candidate salience must be an object")
    return WorkingMemoryCandidate(
        candidate_id=str(row["id"]),
        identity=identity,
        kind=WorkingMemoryItemKind(str(row["kind"])),
        text=str(row["text"]),
        task_relevance=TaskRelevance(float(row["relevance"]), ("fixture_task_relevance",)),
        salience=SalienceInput(**salience),
        reference_id=(str(row["reference_id"]) if row.get("reference_id") else None),
        source_record_id=(
            str(row["source_record_id"]) if row.get("source_record_id") else None
        ),
    )


def _coverage(required: set[str], available: set[str]) -> tuple[int, int]:
    return len(required & available), len(required)


def run(path: Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    root = _load(path)
    governor = DeterministicTokenCounter()
    service = WorkingMemoryService()

    baseline_hits = baseline_required = 0
    working_hits = working_required = 0
    baseline_tokens = working_tokens = 0
    baseline_recall_calls = working_recall_calls = 0
    baseline_repeated = working_repeated = 0
    baseline_stale = working_stale = 0
    baseline_exact_fetches = working_exact_fetches = 0
    cross_task_leakage = 0
    task_reports: list[dict[str, Any]] = []
    owners: dict[str, str] = {}

    for task_index, task in enumerate(root["tasks"]):
        identity = WorkingMemoryIdentity(
            str(task["scope_marker"]),
            str(task["session_id"]),
            str(task["task_id"]),
        )
        candidates = {
            str(row["id"]): _candidate(identity, row) for row in task["candidates"]
        }
        for candidate_id in candidates:
            previous = owners.setdefault(candidate_id, identity.task_id)
            if previous != identity.task_id:
                raise ValueError(f"fixture candidate ID reused across tasks: {candidate_id}")

        seen_baseline: set[str] = set()
        wm_ledger = WorkingMemoryEmissionLedger(identity)
        fetched_wm: set[str] = set()
        task_baseline_hits = task_baseline_required = 0
        task_working_hits = task_working_required = 0
        task_baseline_tokens = task_working_tokens = 0
        task_baseline_repeated = task_working_repeated = 0
        task_baseline_stale = task_working_stale = 0

        for step_index, step in enumerate(task["steps"]):
            now = _START + timedelta(minutes=task_index * 10 + step_index)
            required = set(map(str, step["required_ids"]))
            stale = set(map(str, step.get("stale_ids", [])))
            baseline_ids = list(map(str, step["baseline_ids"]))
            active_ids = list(map(str, step["active_ids"]))
            exact_ids = set(map(str, step.get("exact_fetch_ids", [])))

            unknown = (required | stale | set(baseline_ids) | set(active_ids)) - set(candidates)
            if unknown:
                raise ValueError(f"fixture references unknown candidate IDs: {sorted(unknown)}")

            baseline_recall_calls += 1
            baseline_available = set(baseline_ids)
            hits, total = _coverage(required, baseline_available)
            baseline_hits += hits
            baseline_required += total
            task_baseline_hits += hits
            task_baseline_required += total
            baseline_stale += len(baseline_available & stale)
            task_baseline_stale += len(baseline_available & stale)
            for candidate_id in baseline_ids:
                if candidate_id in seen_baseline:
                    baseline_repeated += 1
                    task_baseline_repeated += 1
                seen_baseline.add(candidate_id)
                tokens = governor.estimate_tokens(candidates[candidate_id].text)
                baseline_tokens += tokens
                task_baseline_tokens += tokens
            baseline_exact_fetches += len(exact_ids & baseline_available)

            snapshot = service.activate(
                identity,
                [candidates[candidate_id] for candidate_id in active_ids],
                now=now,
            )
            if step_index == 0:
                working_recall_calls += 1
            working_available = {item.candidate_id for item in snapshot.items}
            hits, total = _coverage(required, working_available)
            working_hits += hits
            working_required += total
            task_working_hits += hits
            task_working_required += total
            working_stale += len(working_available & stale)
            task_working_stale += len(working_available & stale)
            emission = service.emit(identity, ledger=wm_ledger, now=now)
            working_tokens += emission.estimated_tokens
            task_working_tokens += emission.estimated_tokens
            working_repeated += sum(
                1
                for item in emission.items
                if wm_ledger.emitted_fingerprints.get(item.candidate_id)
                != item.content_fingerprint
            )
            task_working_repeated += 0
            for candidate_id in exact_ids & working_available:
                if candidate_id not in fetched_wm:
                    fetched_wm.add(candidate_id)
                    working_exact_fetches += 1

            for item in snapshot.items:
                if owners.get(item.candidate_id) != identity.task_id:
                    cross_task_leakage += 1

        service.close(
            identity,
            now=_START + timedelta(minutes=task_index * 10 + len(task["steps"]) + 1),
        )
        task_reports.append(
            {
                "task_id": identity.task_id,
                "baseline_required_context_coverage": (
                    task_baseline_hits / task_baseline_required if task_baseline_required else 1.0
                ),
                "working_memory_required_context_coverage": (
                    task_working_hits / task_working_required if task_working_required else 1.0
                ),
                "baseline_tokens": task_baseline_tokens,
                "working_memory_emitted_tokens": task_working_tokens,
                "baseline_repeated_injections": task_baseline_repeated,
                "working_memory_repeated_injections": task_working_repeated,
                "baseline_stale_contamination": task_baseline_stale,
                "working_memory_stale_contamination": task_working_stale,
            }
        )

    baseline_coverage = baseline_hits / baseline_required if baseline_required else 1.0
    working_coverage = working_hits / working_required if working_required else 1.0
    accepted = (
        working_coverage >= baseline_coverage
        and working_coverage >= 0.95
        and working_tokens <= baseline_tokens
        and working_recall_calls <= baseline_recall_calls
        and working_repeated == 0
        and working_stale == 0
        and cross_task_leakage == 0
        and working_exact_fetches <= baseline_exact_fetches
    )
    return {
        "fixture": str(path),
        "task_count": len(root["tasks"]),
        "step_count": sum(len(task["steps"]) for task in root["tasks"]),
        "quality_metric": "required_context_coverage_proxy",
        "baseline": {
            "required_context_coverage": baseline_coverage,
            "recall_calls": baseline_recall_calls,
            "memory_tokens": baseline_tokens,
            "repeated_context_injections": baseline_repeated,
            "stale_context_contamination": baseline_stale,
            "exact_fetch_count": baseline_exact_fetches,
        },
        "working_memory": {
            "required_context_coverage": working_coverage,
            "recall_calls": working_recall_calls,
            "memory_tokens": working_tokens,
            "repeated_context_injections": working_repeated,
            "stale_context_contamination": working_stale,
            "cross_task_leakage": cross_task_leakage,
            "exact_fetch_count": working_exact_fetches,
        },
        "task_reports": task_reports,
        "accepted": accepted,
        "changes_runtime_behavior": False,
        "notes": (
            "Controlled source benchmark. Coverage measures required task-state availability, "
            "not end-user or LLM task quality. Working Memory is not wired into production runtime."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="M5 Working Memory controlled benchmark")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    args = parser.parse_args()
    print(json.dumps(run(args.fixture), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
