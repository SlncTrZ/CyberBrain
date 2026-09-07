# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime

from cyberbrain.dreaming.engine import DreamingEngine
from cyberbrain.dreaming.planner import EpisodeSnippet
from cyberbrain.dreaming.reasoner import (
    DreamCandidate,
    DreamReasoningResult,
    EvidenceItem,
)


class FakeRetriever:
    def recall(self, *, topic, bucket, limit):  # noqa: ANN001
        return [
            EvidenceItem(
                id=f"{topic}-1",
                record_type="episode",
                content=f"Historical evidence about {topic}",
                score=0.9,
                event_time=bucket.end,
                metadata={"bucket": bucket.name},
            )
        ]


class FakeReasoner:
    def reason(self, request):  # noqa: ANN001
        topic = request.focal_topics[0]
        ids = [item.id for item in request.evidence_by_topic[topic]]
        return DreamReasoningResult(
            request_id=request.request_id,
            candidates=[
                DreamCandidate(
                    entity_name="cyberbrain_architecture",
                    entity_type="lesson",
                    summary="CyberBrain should own generic memory infrastructure.",
                    content="MeiLin should consume CyberBrain rather than own it.",
                    evidence_ids=ids,
                    confidence=0.95,
                    classification="evolution",
                )
            ],
        )


def test_dry_run_collects_deduplicated_evidence_and_candidates() -> None:
    episodes = [
        EpisodeSnippet(
            content="CyberBrain replaces MeiLin-owned memory infrastructure.",
            event_time=datetime(2026, 9, 4, 1, 0, tzinfo=UTC),
        ),
        EpisodeSnippet(
            content="CyberBrain Dreaming consolidates experience.",
            event_time=datetime(2026, 9, 4, 2, 0, tzinfo=UTC),
        ),
    ]
    result = DreamingEngine(
        retriever=FakeRetriever(),
        reasoner=FakeReasoner(),
    ).dry_run(episodes, session_id="session-1", topic_limit=1)

    assert result.request.session_id == "session-1"
    assert result.request.focal_topics == ["CyberBrain"]
    assert len(result.request.evidence_by_topic["CyberBrain"]) == 1
    assert result.result.candidates[0].classification == "evolution"
    assert result.result.candidates[0].confidence == 0.95


def test_prepare_request_filters_explicit_cross_project_evidence() -> None:
    class ScopedRetriever:
        def recall(self, *, topic, bucket, limit):  # noqa: ANN001
            del topic, limit
            return [
                EvidenceItem(
                    id="matching-project",
                    record_type="knowledge",
                    content="CyberBrain matching evidence",
                    score=0.9,
                    event_time=bucket.end,
                    metadata={"project": "Slnc_Pi"},
                ),
                EvidenceItem(
                    id="missing-project",
                    record_type="knowledge",
                    content="CyberBrain evidence without project metadata",
                    score=0.8,
                    event_time=bucket.end,
                    metadata={},
                ),
                EvidenceItem(
                    id="wrong-project",
                    record_type="knowledge",
                    content="CyberBrain evidence from wrong project",
                    score=0.95,
                    event_time=bucket.end,
                    metadata={"project": "TCDserver"},
                ),
            ]

    class ScopedAssociative:
        def expand(self, *, seed, bucket):  # noqa: ANN001
            del seed
            return [
                EvidenceItem(
                    id="assoc-matching",
                    record_type="episode",
                    content="CyberBrain associative matching evidence",
                    score=0.85,
                    event_time=bucket.end,
                    metadata={"project": "Slnc_Pi"},
                ),
                EvidenceItem(
                    id="assoc-wrong",
                    record_type="episode",
                    content="CyberBrain associative evidence from wrong project",
                    score=0.99,
                    event_time=bucket.end,
                    metadata={"project": "pi"},
                ),
            ]

    episodes = [
        EpisodeSnippet(
            content="CyberBrain Dreaming consolidates experience.",
            event_time=datetime(2026, 9, 4, 2, 0, tzinfo=UTC),
            project="Slnc_Pi",
        )
    ]
    engine = DreamingEngine(
        retriever=ScopedRetriever(),
        reasoner=FakeReasoner(),
        associative_expander=ScopedAssociative(),
    )

    request = engine.prepare_request(
        episodes,
        session_id="session-scoped",
        focal_topics=["CyberBrain"],
    )

    ids = [item.id for item in request.evidence_by_topic["CyberBrain"]]
    assert ids == ["matching-project", "missing-project", "assoc-matching"]


def test_prepare_request_then_reason_matches_dry_run_contract() -> None:
    episodes = [
        EpisodeSnippet(
            content="CyberBrain Dreaming consolidates experience.",
            event_time=datetime(2026, 9, 4, 2, 0, tzinfo=UTC),
        )
    ]
    engine = DreamingEngine(
        retriever=FakeRetriever(),
        reasoner=FakeReasoner(),
    )

    request = engine.prepare_request(
        episodes,
        session_id="session-prepare",
        topic_limit=1,
    )
    prepared = engine.reason_prepared(request)

    assert prepared.request is request
    assert prepared.result.request_id == request.request_id
    assert prepared.result.candidates[0].classification == "evolution"
