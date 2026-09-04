# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime

from cyberbrain.dreaming.associative import BoundedAssociativeRecall
from cyberbrain.dreaming.planner import TemporalBucket
from cyberbrain.dreaming.reasoner import EvidenceItem


class FakeRecall:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def recall(self, *, topic: str, bucket: TemporalBucket, limit: int) -> list[EvidenceItem]:
        self.queries.append(topic)
        now = datetime(2026, 8, 20, tzinfo=UTC)
        mapping = {
            "Slnc_VideoAdapter": [
                EvidenceItem(
                    id="depth1",
                    record_type="knowledge",
                    content="Depth one evidence",
                    score=0.9,
                    event_time=now,
                    metadata={"entity_name": "OpenMontage", "topic": "video_stack"},
                )
            ],
            "OpenMontage": [
                EvidenceItem(
                    id="depth2",
                    record_type="knowledge",
                    content="Depth two evidence",
                    score=0.85,
                    event_time=now,
                    metadata={"entity_name": "ffmpeg", "topic": "video_stack"},
                )
            ],
            "video_stack": [
                EvidenceItem(
                    id="depth2b",
                    record_type="knowledge",
                    content="Alternative depth two evidence",
                    score=0.8,
                    event_time=now,
                    metadata={"entity_name": "vmk"},
                )
            ],
        }
        return mapping.get(topic, [])[:limit]


def _bucket() -> TemporalBucket:
    return TemporalBucket(
        name="1_to_4_weeks",
        start=datetime(2026, 8, 1, tzinfo=UTC),
        end=datetime(2026, 8, 28, tzinfo=UTC),
    )


def test_associative_recall_expands_to_depth_two_and_tags_provenance() -> None:
    recall = FakeRecall()
    expander = BoundedAssociativeRecall(
        retriever=recall,
        max_depth=2,
        per_query_limit=2,
        total_limit=4,
    )
    seed = [
        EvidenceItem(
            id="seed",
            record_type="knowledge",
            content="Seed",
            score=1.0,
            event_time=datetime(2026, 8, 20, tzinfo=UTC),
            metadata={"entity_name": "Slnc_VideoAdapter"},
        )
    ]

    result = expander.expand(seed=seed, bucket=_bucket())

    assert [item.id for item in result][:2] == ["depth1", "depth2"]
    assert result[0].metadata["association_depth"] == 1
    assert result[0].metadata["association_query"] == "Slnc_VideoAdapter"
    assert result[1].metadata["association_depth"] == 2
    assert "ffmpeg" not in recall.queries


def test_associative_recall_never_returns_seed_duplicates() -> None:
    class DuplicateRecall:
        def recall(self, *, topic: str, bucket: TemporalBucket, limit: int) -> list[EvidenceItem]:
            return [
                EvidenceItem(
                    id="seed",
                    record_type="knowledge",
                    content="duplicate",
                    score=0.9,
                    event_time=datetime(2026, 8, 20, tzinfo=UTC),
                    metadata={},
                )
            ]

    expander = BoundedAssociativeRecall(retriever=DuplicateRecall())
    seed = [
        EvidenceItem(
            id="seed",
            record_type="knowledge",
            content="Seed",
            score=1.0,
            event_time=datetime(2026, 8, 20, tzinfo=UTC),
            metadata={"topic": "CyberBrain"},
        )
    ]

    assert expander.expand(seed=seed, bucket=_bucket()) == []
