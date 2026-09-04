# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,}")
_DEFAULT_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "been",
    "before",
    "being",
    "from",
    "have",
    "into",
    "just",
    "more",
    "need",
    "that",
    "then",
    "there",
    "they",
    "this",
    "using",
    "with",
    "would",
}


@dataclass(frozen=True)
class EpisodeSnippet:
    content: str
    event_time: datetime


@dataclass(frozen=True)
class TemporalBucket:
    name: str
    start: datetime | None
    end: datetime


@dataclass(frozen=True)
class DreamPlan:
    focal_topics: list[str]
    buckets: list[TemporalBucket]
    session_start: datetime
    session_end: datetime


class TopicExtractor:
    def __init__(self, *, stopwords: set[str] | None = None) -> None:
        self._stopwords = set(stopwords or _DEFAULT_STOPWORDS)

    def extract(self, texts: Iterable[str], *, limit: int = 5) -> list[str]:
        counts: Counter[str] = Counter()
        display: dict[str, str] = {}

        for text in texts:
            for token in _TOKEN_RE.findall(text):
                normalized = token.casefold()
                if normalized in self._stopwords or normalized.isdigit():
                    continue
                counts[normalized] += 1
                display.setdefault(normalized, token)

        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [display[token] for token, _count in ranked[:limit]]


class DreamingPlanner:
    def __init__(self, *, extractor: TopicExtractor | None = None) -> None:
        self._extractor = extractor or TopicExtractor()

    def plan(self, episodes: list[EpisodeSnippet], *, topic_limit: int = 3) -> DreamPlan:
        if not episodes:
            raise ValueError("cannot build a dream plan from an empty session")

        normalized_times = [self._utc(episode.event_time) for episode in episodes]
        session_start = min(normalized_times)
        session_end = max(normalized_times)
        topics = self._extractor.extract(
            (episode.content for episode in episodes),
            limit=topic_limit,
        )
        if not topics:
            raise ValueError("session did not contain usable focal topics")

        return DreamPlan(
            focal_topics=topics,
            buckets=self._build_buckets(session_end),
            session_start=session_start,
            session_end=session_end,
        )

    def _build_buckets(self, now: datetime) -> list[TemporalBucket]:
        one_week = now - timedelta(days=7)
        four_weeks = now - timedelta(days=28)
        three_months = now - timedelta(days=90)
        six_months = now - timedelta(days=180)
        one_year = now - timedelta(days=365)

        return [
            TemporalBucket("older_than_1y", None, one_year),
            TemporalBucket("6_to_12_months", one_year, six_months),
            TemporalBucket("3_to_6_months", six_months, three_months),
            TemporalBucket("1_to_3_months", three_months, four_weeks),
            TemporalBucket("1_to_4_weeks", four_weeks, one_week),
            TemporalBucket("last_week", one_week, now),
        ]

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("episode event_time must be timezone-aware")
        return value.astimezone(UTC)
