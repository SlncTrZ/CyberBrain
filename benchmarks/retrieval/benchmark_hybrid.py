# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime

from cyberbrain.retrieval.benchmark import BenchmarkCase, BenchmarkEvaluator
from cyberbrain.retrieval.engine import HybridRetrievalEngine
from cyberbrain.retrieval.models import RankedHit, RetrievalHit, RetrievalIntent

HITS = [
    RetrievalHit(
        "release-old",
        text="Release service version 1 commit old111 passed CI and was deployed.",
        project="gateway",
        topic="release",
        entity_name="service-release",
        status="superseded",
    ),
    RetrievalHit(
        "release-current",
        text="Current release service version 2 commit new222 passed CI and is the active release.",
        project="gateway",
        topic="release",
        entity_name="service-release",
        status="active",
    ),
    RetrievalHit(
        "rule-sync",
        text=(
            "Provider schema drift must fail closed and requires catalog test sync "
            "before calls resume."
        ),
        project="gateway",
        topic="provider-contract",
        status="active",
    ),
    RetrievalHit(
        "event-sync",
        text=(
            "Deployment event: provider schema changed; gateway rejected calls; "
            "operator ran catalog sync."
        ),
        project="gateway",
        topic="deployment",
        event_time=datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
    ),
    RetrievalHit(
        "other-project",
        text="Agent adapter token budget is 1000 tokens with compact bootstrap.",
        project="other",
        topic="agent-adapter",
        status="active",
    ),
    RetrievalHit(
        "target-project",
        text=(
            "Agent adapter token budget is 1000 tokens with compact bootstrap and "
            "duplicate suppression."
        ),
        project="cyberbrain",
        topic="agent-adapter",
        status="active",
    ),
    RetrievalHit(
        "event-past",
        text="Deployment health result was healthy after compact recall rollout.",
        project="cyberbrain",
        topic="deployment",
        event_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
    ),
    RetrievalHit(
        "event-future",
        text="Deployment health result was healthy after a later retrieval rollout.",
        project="cyberbrain",
        topic="deployment",
        event_time=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
    ),
    RetrievalHit(
        "identifier-exact",
        text="Contract fingerprint zx9-77 belongs to the compact recall provider schema.",
        project="cyberbrain",
        topic="provider-contract",
        status="active",
    ),
    RetrievalHit(
        "identifier-generic",
        text="Provider contract fingerprint changes when tool schemas change.",
        project="cyberbrain",
        topic="provider-contract",
        status="active",
    ),
    RetrievalHit(
        "config-v1",
        text="Adapter configuration revision one used a 1600 token bootstrap budget.",
        project="cyberbrain",
        topic="adapter-config",
        entity_name="adapter-policy",
        status="superseded",
    ),
    RetrievalHit(
        "config-v2",
        text="Adapter configuration revision two uses a 1000 token bootstrap budget.",
        project="cyberbrain",
        topic="adapter-config",
        entity_name="adapter-policy",
        status="active",
    ),
]

CASES = [
    BenchmarkCase(
        "current-vs-superseded",
        "current active release commit",
        RetrievalIntent.CURRENT_FACT,
        expected_ids=("release-current",),
        forbidden_ids=("release-old",),
        project="gateway",
        topic="release",
        entity_name="service-release",
        status="active",
        notes="Pattern derived from real same-identity active/superseded Knowledge groups.",
    ),
    BenchmarkCase(
        "event-vs-rule",
        "what rule applies after provider schema drift catalog sync",
        RetrievalIntent.CURRENT_FACT,
        expected_ids=("rule-sync",),
        acceptable_ids=("event-sync",),
        project="gateway",
        status="active",
        notes="Pattern derived from operational-event versus reusable-rule semantic debt.",
    ),
    BenchmarkCase(
        "project-contamination",
        "agent adapter token budget duplicate suppression",
        RetrievalIntent.PROJECT_SCOPED,
        expected_ids=("target-project",),
        forbidden_ids=("other-project",),
        project="cyberbrain",
        topic="agent-adapter",
        status="active",
        notes="Same lexical subject appears in another project.",
    ),
    BenchmarkCase(
        "temporal-cutoff",
        "deployment health result",
        RetrievalIntent.TEMPORAL,
        expected_ids=("event-past",),
        forbidden_ids=("event-future",),
        project="cyberbrain",
        topic="deployment",
        not_after=datetime(2026, 1, 2, tzinfo=UTC),
        notes="Future event must not leak across point-in-time recall.",
    ),
    BenchmarkCase(
        "exact-identifier",
        "zx9-77 contract fingerprint",
        RetrievalIntent.CURRENT_FACT,
        expected_ids=("identifier-exact",),
        project="cyberbrain",
        topic="provider-contract",
        status="active",
        notes="Exact identifiers are a common lexical weakness of vector-only recall.",
    ),
    BenchmarkCase(
        "active-config-evolution",
        "adapter configuration 1000 token bootstrap active revision",
        RetrievalIntent.TIMELINE,
        expected_ids=("config-v1", "config-v2"),
        project="cyberbrain",
        topic="adapter-config",
        entity_name="adapter-policy",
        notes="Pattern derived from versioned active/superseded Knowledge timelines.",
    ),
]

SEMANTIC = {
    "current-vs-superseded": ("release-old", "release-current", "rule-sync"),
    "event-vs-rule": ("event-sync", "rule-sync", "release-current"),
    "project-contamination": ("other-project", "target-project", "config-v2"),
    "temporal-cutoff": ("event-future", "event-past", "event-sync"),
    "exact-identifier": ("identifier-generic", "identifier-exact", "rule-sync"),
    "active-config-evolution": ("config-v1", "config-v2", "target-project"),
}


def _ranked_from_lexical(result) -> list[RankedHit]:
    return list(result.lexical)


def run() -> dict[str, object]:
    engine = HybridRetrievalEngine(HITS)
    evaluator = BenchmarkEvaluator(k=3)
    texts = {hit.id: hit.text for hit in HITS}
    times = {hit.id: hit.event_time for hit in HITS if hit.event_time is not None}

    def make_runner(channel: str):
        def runner(case: BenchmarkCase):
            result = engine.query(
                case.query,
                semantic_ranked_ids=SEMANTIC[case.case_id],
                project=case.project,
                topic=case.topic,
                entity_name=case.entity_name,
                status=case.status,
                not_after=case.not_after,
            )
            if channel == "semantic":
                ranked = list(result.semantic)
            elif channel == "lexical":
                ranked = _ranked_from_lexical(result)
            else:
                ranked = list(result.hybrid)
            return ranked, texts, times

        return runner

    reports = {
        name: evaluator.run(CASES, make_runner(name)) for name in ("semantic", "lexical", "hybrid")
    }
    return {
        "case_count": len(CASES),
        "fixture_kind": "sanitized structural cases derived from audited corpus failure patterns",
        "reports": {name: asdict(report) for name, report in reports.items()},
        "caution": (
            "small reviewed Wave-1 fixture; use to validate harness/direction, "
            "not claim production superiority"
        ),
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
