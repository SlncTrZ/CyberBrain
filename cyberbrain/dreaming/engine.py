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
from cyberbrain.dreaming.relevance import TopicRelevanceGuard


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
        relevance_guard: TopicRelevanceGuard | None = None,
        per_bucket_limit: int = 5,
    ) -> None:
        self._retriever = retriever
        self._reasoner = reasoner
        self._planner = planner or DreamingPlanner()
        self._associative_expander = associative_expander
        self._relevance_guard = relevance_guard or TopicRelevanceGuard()
        self._per_bucket_limit = per_bucket_limit

    def prepare_request(
        self,
        episodes: list[EpisodeSnippet],
        *,
        session_id: str,
        topic_limit: int = 3,
        focal_topics: list[str] | None = None,
    ) -> DreamReasoningRequest:
        plan = self._planner.plan(episodes, topic_limit=topic_limit)
        topics = self._normalize_topics(focal_topics) if focal_topics else plan.focal_topics
        session_project = self._stable_session_project(episodes)
        evidence: dict[str, list[EvidenceItem]] = {}

        for topic in topics:
            topic_evidence = self._session_evidence(
                episodes,
                session_id=session_id,
                topic=topic,
            )
            for bucket in plan.buckets:
                direct = self._relevance_guard.filter_evidence(
                    topic=topic,
                    items=self._filter_project_scope(
                        self._retriever.recall(
                            topic=topic,
                            bucket=bucket,
                            limit=self._per_bucket_limit,
                        ),
                        session_project=session_project,
                    ),
                )
                topic_evidence.extend(direct)
                if self._associative_expander is not None:
                    expanded = self._associative_expander.expand(
                        seed=direct,
                        bucket=bucket,
                    )
                    topic_evidence.extend(
                        self._relevance_guard.filter_evidence(
                            topic=topic,
                            items=self._filter_project_scope(
                                expanded,
                                session_project=session_project,
                            ),
                        )
                    )
            evidence[topic] = self._deduplicate(topic_evidence)

        return DreamReasoningRequest(
            request_id=str(uuid4()),
            session_id=session_id,
            focal_topics=topics,
            session_start=plan.session_start,
            session_end=plan.session_end,
            evidence_by_topic=evidence,
        )

    def reason_prepared(self, request: DreamReasoningRequest) -> DreamDryRunResult:
        result = self._reasoner.reason(request)
        if result.request_id != request.request_id:
            raise ValueError("reasoner response request_id does not match request")
        return DreamDryRunResult(request=request, result=result)

    def dry_run(
        self,
        episodes: list[EpisodeSnippet],
        *,
        session_id: str,
        topic_limit: int = 3,
        focal_topics: list[str] | None = None,
    ) -> DreamDryRunResult:
        request = self.prepare_request(
            episodes,
            session_id=session_id,
            topic_limit=topic_limit,
            focal_topics=focal_topics,
        )
        return self.reason_prepared(request)

    def _session_evidence(
        self,
        episodes: list[EpisodeSnippet],
        *,
        session_id: str,
        topic: str,
    ) -> list[EvidenceItem]:
        result: list[EvidenceItem] = []
        for episode in episodes:
            evidence_id = str(episode.evidence_id or "").strip()
            if not evidence_id:
                continue
            excerpt = self._relevance_guard.topic_excerpt(
                topic=topic,
                text=episode.content,
            )
            if not excerpt:
                continue
            metadata = {
                "session_id": session_id,
                "source": "session_episode",
                "direct_session": True,
            }
            if episode.project:
                metadata["project"] = episode.project
            result.append(
                EvidenceItem(
                    id=evidence_id,
                    record_type="episode",
                    content=excerpt,
                    score=1.0,
                    event_time=episode.event_time,
                    metadata=metadata,
                )
            )
        return result

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
    def _stable_session_project(episodes: list[EpisodeSnippet]) -> str | None:
        projects: dict[str, str] = {}
        for episode in episodes:
            value = str(episode.project or "").strip()
            if value:
                projects.setdefault(value.casefold(), value)
        if len(projects) != 1:
            return None
        return next(iter(projects.values()))

    @staticmethod
    def _filter_project_scope(
        items: list[EvidenceItem],
        *,
        session_project: str | None,
    ) -> list[EvidenceItem]:
        if not session_project:
            return list(items)
        normalized_session = session_project.casefold()
        result: list[EvidenceItem] = []
        for item in items:
            evidence_project = str(item.metadata.get("project") or "").strip()
            if evidence_project and evidence_project.casefold() != normalized_session:
                continue
            result.append(item)
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
