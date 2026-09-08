# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cyberbrain.retrieval.baseline import PreRankedBaseline
from cyberbrain.retrieval.benchmark import BenchmarkCase, BenchmarkEvaluator
from cyberbrain.retrieval.engine import HybridRetrievalEngine
from cyberbrain.retrieval.fusion import FusionCandidate, ReciprocalRankFusion
from cyberbrain.retrieval.lexical import BM25Document, BM25Scorer, tokenize
from cyberbrain.retrieval.models import RankedHit, RetrievalHit, RetrievalIntent
from cyberbrain.retrieval.signals import ScopeTemporalSignals


def test_tokenize_is_casefolded_and_deterministic() -> None:
    assert tokenize("Release V0.1.7 release") == ("release", "v0.1.7", "release")


def test_bm25_deterministic_and_exact_identifier_friendly() -> None:
    docs = [
        BM25Document("a", "release commit abc123 passed CI"),
        BM25Document("b", "release planning notes"),
    ]
    scorer = BM25Scorer(docs)
    first = scorer.score("abc123 CI")
    second = scorer.score("abc123 CI")
    assert first == second
    assert first[0][0] == "a"
    assert first[0][1] > first[1][1]


def test_bm25_empty_documents_and_query() -> None:
    assert BM25Scorer([]).score("anything") == []
    rows = BM25Scorer([BM25Document("a", "text")]).score("")
    assert rows == [("a", 0.0)]


def test_pre_ranked_baseline_preserves_input_order() -> None:
    rows = PreRankedBaseline(("b", "a")).results()
    assert [row.id for row in rows] == ["b", "a"]


def test_scope_signal_rejects_explicit_project_mismatch() -> None:
    allowed, reasons = ScopeTemporalSignals().contributions(
        RetrievalHit("x", project="other"), project="target"
    )
    assert allowed is False
    assert reasons == {"project_mismatch": -1.0}


def test_status_signal_rejects_lifecycle_mismatch() -> None:
    allowed, reasons = ScopeTemporalSignals().contributions(
        RetrievalHit("x", status="superseded"), status="active"
    )
    assert allowed is False
    assert reasons == {"status_mismatch": -1.0}


def test_temporal_signal_rejects_future_event() -> None:
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    allowed, reasons = ScopeTemporalSignals().contributions(
        RetrievalHit("x", event_time=cutoff + timedelta(days=1)), not_after=cutoff
    )
    assert allowed is False
    assert reasons == {"future_ineligible": -1.0}


def test_scope_signal_exposes_positive_reason_codes() -> None:
    hit = RetrievalHit("x", project="p", topic="t", entity_name="e", status="active")
    allowed, reasons = ScopeTemporalSignals().contributions(
        hit, project="p", topic="t", entity_name="e"
    )
    assert allowed is True
    assert set(reasons) == {"project_match", "topic_match", "entity_match", "active_status"}


def test_rrf_is_deterministic_and_explainable() -> None:
    hit_a = RetrievalHit("a", status="active")
    hit_b = RetrievalHit("b", status="active")
    fusion = ReciprocalRankFusion()
    candidates = [
        FusionCandidate(hit_a, semantic_rank=2, lexical_rank=1),
        FusionCandidate(hit_b, semantic_rank=1, lexical_rank=2),
    ]
    first = fusion.fuse(candidates)
    second = fusion.fuse(candidates)
    assert first == second
    assert set(first[0].contributions) >= {"semantic_rrf", "lexical_rrf", "active_status"}


def test_rrf_merges_duplicate_candidate_channels() -> None:
    hit = RetrievalHit("a")
    rows = ReciprocalRankFusion().fuse(
        [
            FusionCandidate(hit, semantic_rank=1),
            FusionCandidate(hit, lexical_rank=1),
        ]
    )
    assert len(rows) == 1
    assert set(rows[0].contributions) == {"semantic_rrf", "lexical_rrf"}


def test_rrf_handles_missing_channel() -> None:
    rows = ReciprocalRankFusion().fuse([FusionCandidate(RetrievalHit("a"), lexical_rank=1)])
    assert rows[0].id == "a"
    assert "semantic_rrf" not in rows[0].contributions
    assert "lexical_rrf" in rows[0].contributions


def test_hybrid_engine_lexical_fallback_when_semantic_missing() -> None:
    engine = HybridRetrievalEngine(
        [
            RetrievalHit("exact", text="gateway contract hash abc123"),
            RetrievalHit("other", text="generic gateway documentation"),
        ]
    )
    result = engine.query("abc123", semantic_ranked_ids=())
    assert result.semantic == ()
    assert result.lexical[0].id == "exact"
    assert result.hybrid[0].id == "exact"


def test_hybrid_engine_filters_scope_contamination() -> None:
    engine = HybridRetrievalEngine(
        [
            RetrievalHit("wrong", text="same feature exact token", project="other"),
            RetrievalHit("right", text="same feature exact token", project="target"),
        ]
    )
    result = engine.query("same feature", semantic_ranked_ids=("wrong", "right"), project="target")
    assert [row.id for row in result.hybrid] == ["right"]


def test_hybrid_engine_filters_future_event() -> None:
    cutoff = datetime(2026, 1, 2, tzinfo=UTC)
    engine = HybridRetrievalEngine(
        [
            RetrievalHit("past", text="deployment result", event_time=cutoff - timedelta(days=1)),
            RetrievalHit("future", text="deployment result", event_time=cutoff + timedelta(days=1)),
        ]
    )
    result = engine.query(
        "deployment result", semantic_ranked_ids=("future", "past"), not_after=cutoff
    )
    assert [row.id for row in result.hybrid] == ["past"]


def test_active_status_can_break_equal_rank_tie() -> None:
    fusion = ReciprocalRankFusion()
    rows = fusion.fuse(
        [
            FusionCandidate(
                RetrievalHit("old", status="superseded"), semantic_rank=1, lexical_rank=1
            ),
            FusionCandidate(RetrievalHit("new", status="active"), semantic_rank=1, lexical_rank=1),
        ]
    )
    assert rows[0].id == "new"


def test_benchmark_metrics_are_correct() -> None:
    case = BenchmarkCase(
        "c1",
        "query",
        RetrievalIntent.PROJECT_SCOPED,
        expected_ids=("right",),
        forbidden_ids=("wrong",),
    )
    metric = BenchmarkEvaluator(k=2).evaluate_case(
        case,
        [RankedHit("wrong", 1.0), RankedHit("right", 0.5)],
        text_by_id={"wrong": "x" * 8, "right": "y" * 8},
    )
    assert metric.recall_at_k == 1.0
    assert metric.reciprocal_rank == 0.5
    assert metric.contamination_rate == 0.5
    assert metric.returned_token_estimate == 4


def test_benchmark_temporal_correctness_detects_future_result() -> None:
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    case = BenchmarkCase(
        "c1", "query", RetrievalIntent.TEMPORAL, expected_ids=("past",), not_after=cutoff
    )
    metric = BenchmarkEvaluator(k=2).evaluate_case(
        case,
        [RankedHit("past", 1.0), RankedHit("future", 0.5)],
        event_time_by_id={
            "past": cutoff - timedelta(days=1),
            "future": cutoff + timedelta(days=1),
        },
    )
    assert metric.temporal_correct is False


def test_benchmark_aggregate_by_intent() -> None:
    evaluator = BenchmarkEvaluator(k=1)
    case_a = BenchmarkCase("a", "q", RetrievalIntent.CURRENT_FACT, expected_ids=("x",))
    case_b = BenchmarkCase("b", "q", RetrievalIntent.HISTORICAL_EVENT, expected_ids=("y",))
    report = evaluator.aggregate(
        [
            (case_a, evaluator.evaluate_case(case_a, [RankedHit("x", 1.0)])),
            (case_b, evaluator.evaluate_case(case_b, [RankedHit("y", 1.0)])),
        ]
    )
    assert report.cases == 2
    assert report.mean_recall_at_k == 1.0
    assert set(report.by_intent) == {"current_fact", "historical_event"}


def test_benchmark_case_requires_expected_id() -> None:
    try:
        BenchmarkCase("c", "q", RetrievalIntent.CURRENT_FACT, expected_ids=())
    except ValueError as exc:
        assert "expected_ids" in str(exc)
    else:
        raise AssertionError("expected ValueError")
