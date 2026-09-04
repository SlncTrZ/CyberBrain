# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from cyberbrain.dreaming.planner import DreamingPlanner, EpisodeSnippet, TemporalBucket
from cyberbrain.dreaming.reasoner import (
    DreamReasoner,
    DreamReasoningRequest,
    DreamReasoningResult,
    EvidenceItem,
)


@dataclass(frozen=True)
class DreamDryRunResult:
    request: DreamReasoningRequest
    result: DreamReasoningResult


class EvidenceRetriever(Protocol):
    def recall(
        self,
        *,
        topic: str,
        bucket: TemporalBucket,
        limit: int,
    ) -> list[EvidenceItem]: ...


class AssociativeExpander(Protocol):
    def expand(
        self,
        *,
        seed: list[EvidenceItem],
        bucket: TemporalBucket,
    ) -> list[EvidenceItem]: ...


class DreamingEngine:
    def __init__(
        self,
        *,
        retriever: EvidenceRetriever,
        reasoner: DreamReasoner,
        planner: DreamingPlanner | None = None,
        associative_expander: AssociativeExpander | None = None,
        per_bucket_limit: int = 5,
    ) -> None:
        self._retriever = retriever
        self._reasoner = reasoner
        self._planner = planner or DreamingPlanner()
        self._associative_expander = associative_expander
        self._per_bucket_limit = per_bucket_limit

    def dry_run(
        self,
        episodes: list[EpisodeSnippet],
        *,
        session_id: str,
        topic_limit: int = 3,
        focal_topics: list[str] | None = None,
    ) -> DreamDryRunResult:
        plan = self._planner.plan(episodes, topic_limit=topic_limit)
        topics = self._normalize_topics(focal_topics) if focal_topics else plan.focal_topics
        evidence: dict[str, list[EvidenceItem]] = {}

        for topic in topics:
            topic_evidence: list[EvidenceItem] = []
            for bucket in plan.buckets:
                direct = self._retriever.recall(
                    topic=topic,
                    bucket=bucket,
                    limit=self._per_bucket_limit,
                )
                topic_evidence.extend(direct)
                if self._associative_expander is not None:
                    topic_evidence.extend(
                        self._associative_expander.expand(
                            seed=direct,
                            bucket=bucket,
                        )
                    )
            evidence[topic] = self._deduplicate(topic_evidence)

        request = DreamReasoningRequest(
            request_id=str(uuid4()),
            session_id=session_id,
            focal_topics=topics,
            session_start=plan.session_start,
            session_end=plan.session_end,
            evidence_by_topic=evidence,
        )
        result = self._reasoner.reason(request)
        if result.request_id != request.request_id:
            raise ValueError("reasoner response request_id does not match request")

        return DreamDryRunResult(request=request, result=result)

    @staticmethod
    def _normalize_topics(topics: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for topic in topics:
            value = topic.strip()
            normalized = value.casefold()
            if not value or normalized in seen:
                continue
            seen.add(normalized)
            result.append(value)
        if not result:
            raise ValueError("focal_topics override must contain at least one non-empty topic")
        return result

    @staticmethod
    def _deduplicate(items: list[EvidenceItem]) -> list[EvidenceItem]:
        seen: set[str] = set()
        result: list[EvidenceItem] = []
        for item in items:
            if item.id in seen:
                continue
            seen.add(item.id)
            result.append(item)
        return result
