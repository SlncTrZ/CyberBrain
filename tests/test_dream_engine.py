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
