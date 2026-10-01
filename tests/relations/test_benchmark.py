# SPDX-License-Identifier: MPL-2.0
from datetime import UTC, datetime

import pytest

from cyberbrain.relations.benchmark import RelationBenchmark, RelationBenchmarkCase, percentile
from cyberbrain.relations.recall import RelationRecallRequest, RelationRecallService
from cyberbrain.relations.traversal import TraversalPolicy
from cyberbrain.retrieval.benchmark import BenchmarkCase
from cyberbrain.retrieval.models import RetrievalIntent
from cyberbrain.tenancy import bind_authority
from tests.relations.test_persistence import owner
from tests.relations.test_traversal import PagedRepository, ready
from tests.tenancy.test_runtime_enforcement import CountingEmbedding


class Instrumented(PagedRepository):
    request_count = 0

    def scroll_page(self, *args, **kwargs):
        self.request_count += 1
        return super().scroll_page(*args, **kwargs)

    def scroll(self, collection, *, qdrant_filter=None, limit=100):
        self.request_count += 1
        return [
            point
            for key, point in self.points.items()
            if self.collections[key] == collection and self.match(point, qdrant_filter or {})
        ][:limit]

    def retrieve(self, *args, **kwargs):
        self.request_count += 1
        return super().retrieve(*args, **kwargs)

    def search(self, *args, **kwargs):
        self.request_count += 1
        return super().search(*args, **kwargs)


def case(records, *, historical=False):
    ids = {name: str(record.id) for name, record in records.items()}
    return RelationBenchmarkCase(
        baseline=BenchmarkCase(
            "controlled",
            "dependency",
            RetrievalIntent.CURRENT_FACT,
            tuple(ids[name] for name in ("b", "c", "d")),
            project="p",
        ),
        request=RelationRecallRequest(
            seed_ids=(records["a"].id,),
            policy=TraversalPolicy(as_of=datetime(2021, 1, 1, tzinfo=UTC) if historical else None),
        ),
        expected_paths=frozenset(
            tuple(ids[node] for node in path)
            for path in (("a", "b"), ("a", "c"), ("a", "b", "d"), ("a", "c", "d"))
        ),
    )


def test_known_seed_benchmark_reports_graph_gold_paths_without_fabricating_baseline_paths():
    repo, records, _, traversal = ready(Instrumented())
    runner = RelationBenchmark(
        repository=repo,
        embedding=CountingEmbedding(),
        collection="knowledge",
        service=RelationRecallService(traversal),
        iterations=2,
    )
    with bind_authority(owner()):
        result = runner.run_case(case(records))
    modes = result["modes"]
    assert modes["relations"]["path_precision"] == 1
    assert modes["relations"]["path_recall"] == 1
    assert modes["relations"]["storage_calls"] == 7
    assert modes["relations"]["embedding_calls"] == 0
    assert modes["vector"]["embedding_calls"] == modes["hybrid"]["embedding_calls"] == 1
    assert modes["vector"]["path_precision"] is None
    assert modes["hybrid"]["path_recall"] is None
    assert all(row["iterations"] == 2 and row["context_tokens"] <= 4096 for row in modes.values())


def test_unsupported_historical_baselines_are_not_scored_as_zero():
    repo, records, _, traversal = ready(Instrumented())
    runner = RelationBenchmark(
        repository=repo,
        embedding=CountingEmbedding(),
        collection="knowledge",
        service=RelationRecallService(traversal),
        iterations=2,
    )
    with bind_authority(owner()):
        result = runner.run_case(case(records, historical=True))
    for mode in ("vector", "hybrid"):
        assert result["modes"][mode]["supported"] is False
        assert "recall_at_k" not in result["modes"][mode]
    assert result["modes"]["relations"]["path_recall"] == 1


def test_percentile_convention_and_empty_sample():
    assert percentile([1, 2, 3, 4, 5], 0.5) == 3
    assert percentile([1, 2, 3, 4, 5], 0.95) == pytest.approx(4.8)
    assert percentile([7], 0.95) == 7
    with pytest.raises(ValueError):
        percentile([], 0.5)
