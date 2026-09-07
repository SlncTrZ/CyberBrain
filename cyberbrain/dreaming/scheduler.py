# SPDX-License-Identifier: MPL-2.0
"""Nightly deterministic Dream enqueue scheduler."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from cyberbrain.dreaming.queue import DreamQueue


@dataclass
class SessionCandidate:
    session_id: str
    latest_event: datetime
    episode_count: int = 0
    topics: Counter[str] = field(default_factory=Counter)
    projects: Counter[str] = field(default_factory=Counter)


def parse_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    if isinstance(value, int | float):
        numeric = float(value)
        seconds = numeric / 1000 if numeric > 10_000_000_000 else numeric
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OSError, OverflowError, ValueError):
            return None
    return None


def qdrant_scroll_pending() -> list[dict[str, Any]]:
    base_url = os.environ.get("CYBERBRAIN_QDRANT_URL", "http://qdrant:6333").rstrip("/")
    collection = os.environ.get(
        "CYBERBRAIN_EPISODIC_COLLECTION",
        "cyberbrain_episodic",
    )
    api_key = (os.environ.get("CYBERBRAIN_QDRANT_API_KEY") or "").strip()
    page_size = int(os.environ.get("CYBERBRAIN_DREAM_SCHEDULER_PAGE_SIZE", "512"))
    max_points = int(os.environ.get("CYBERBRAIN_DREAM_SCHEDULER_MAX_POINTS", "20000"))

    if page_size < 1:
        raise ValueError("CYBERBRAIN_DREAM_SCHEDULER_PAGE_SIZE must be >= 1")
    if max_points < 1:
        raise ValueError("CYBERBRAIN_DREAM_SCHEDULER_MAX_POINTS must be >= 1")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["api-key"] = api_key

    points: list[dict[str, Any]] = []
    offset: object | None = None
    while len(points) < max_points:
        body: dict[str, Any] = {
            "limit": min(page_size, max_points - len(points)),
            "with_payload": True,
            "with_vector": False,
            "filter": {
                "must": [
                    {"key": "dream_status", "match": {"value": "pending"}},
                ]
            },
        }
        if offset is not None:
            body["offset"] = offset

        request = urllib.request.Request(
            f"{base_url}/collections/{collection}/points/scroll",
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        result = payload.get("result") or {}
        batch = result.get("points") or []
        points.extend(batch)
        offset = result.get("next_page_offset")
        if not batch or offset is None:
            break

    if len(points) >= max_points:
        raise RuntimeError(
            f"pending Episode scan reached safety cap {max_points}; refusing partial enqueue"
        )
    return points


def collect_candidates(points: list[dict[str, Any]]) -> dict[str, SessionCandidate]:
    sessions: dict[str, SessionCandidate] = {}
    for point in points:
        payload = point.get("payload") or {}
        session_id = str(payload.get("session_id") or "").strip()
        event_time = parse_time(payload.get("event_time"))
        if not session_id or event_time is None:
            continue

        candidate = sessions.get(session_id)
        if candidate is None:
            candidate = SessionCandidate(session_id=session_id, latest_event=event_time)
            sessions[session_id] = candidate
        candidate.episode_count += 1
        if event_time > candidate.latest_event:
            candidate.latest_event = event_time

        topic = str(payload.get("topic") or "").strip()
        if topic:
            candidate.topics[topic] += 1
        project = str(payload.get("project") or "").strip()
        if project:
            candidate.projects[project] += 1
    return sessions


def top_values(counter: Counter[str], limit: int) -> list[str]:
    if limit < 0:
        raise ValueError("limit must be >= 0")
    return [
        value
        for value, _count in sorted(
            counter.items(),
            key=lambda item: (-item[1], item[0].casefold()),
        )[:limit]
    ]


def run_once(*, dry_run: bool = False) -> dict[str, Any]:
    now = datetime.now(UTC)
    quiet_minutes = int(os.environ.get("CYBERBRAIN_DREAM_SCHEDULER_QUIET_MINUTES", "60"))
    topic_limit = int(os.environ.get("CYBERBRAIN_DREAM_SCHEDULER_TOPIC_LIMIT", "3"))
    if quiet_minutes < 0:
        raise ValueError("CYBERBRAIN_DREAM_SCHEDULER_QUIET_MINUTES must be >= 0")
    if topic_limit < 0:
        raise ValueError("CYBERBRAIN_DREAM_SCHEDULER_TOPIC_LIMIT must be >= 0")

    cutoff = now - timedelta(minutes=quiet_minutes)
    queue = DreamQueue(
        os.environ.get("CYBERBRAIN_DREAM_QUEUE_DB", "/data/dream_queue.sqlite")
    )

    points = qdrant_scroll_pending()
    sessions = collect_candidates(points)
    eligible = 0
    enqueued = 0
    deferred_active = 0
    skipped_existing = 0

    for session_id in sorted(sessions):
        candidate = sessions[session_id]
        if candidate.latest_event > cutoff:
            deferred_active += 1
            continue

        try:
            existing = queue.get_by_session(session_id)
        except KeyError:
            existing = None
        if existing is not None:
            skipped_existing += 1
            continue

        eligible += 1
        topics = top_values(candidate.topics, topic_limit)
        projects = top_values(candidate.projects, 3)
        event = {
            "event": "dream_scheduler_candidate",
            "session_id": session_id,
            "episodes": candidate.episode_count,
            "latest_event": candidate.latest_event.isoformat(),
            "projects": projects,
            "topics": topics,
            "dry_run": dry_run,
        }
        print(json.dumps(event, ensure_ascii=False), flush=True)
        if not dry_run:
            queue.enqueue(session_id, topics)
            enqueued += 1

    summary = {
        "event": "dream_scheduler_summary",
        "run_at": now.isoformat(),
        "pending_points": len(points),
        "pending_sessions": len(sessions),
        "eligible_sessions": eligible,
        "enqueued_sessions": enqueued,
        "deferred_active_sessions": deferred_active,
        "skipped_existing_jobs": skipped_existing,
        "quiet_minutes": quiet_minutes,
        "dry_run": dry_run,
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


def next_run(now: datetime, hour: int, minute: int) -> datetime:
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("scheduler UTC time is out of range")
    current = now.astimezone(UTC) if now.tzinfo else now.replace(tzinfo=UTC)
    target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= current:
        target += timedelta(days=1)
    return target


def parse_schedule(value: str) -> tuple[int, int]:
    schedule = value.strip()
    try:
        hour_text, minute_text = schedule.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except (ValueError, TypeError) as exc:
        raise ValueError("CYBERBRAIN_DREAM_SCHEDULER_UTC must be HH:MM") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("scheduler UTC time is out of range")
    return hour, minute


def run_scheduler() -> None:
    schedule = os.environ.get("CYBERBRAIN_DREAM_SCHEDULER_UTC", "23:50").strip()
    hour, minute = parse_schedule(schedule)

    while True:
        now = datetime.now(UTC)
        target = next_run(now, hour, minute)
        print(
            json.dumps(
                {
                    "event": "dream_scheduler_wait",
                    "schedule_utc": schedule,
                    "next_run": target.isoformat(),
                }
            ),
            flush=True,
        )
        while True:
            remaining = (target - datetime.now(UTC)).total_seconds()
            if remaining <= 0:
                break
            time.sleep(min(remaining, 60.0))
        try:
            run_once(dry_run=False)
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "event": "dream_scheduler_error",
                        "type": type(exc).__name__,
                        "message": str(exc)[:500],
                    }
                ),
                flush=True,
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.once:
        run_once(dry_run=args.dry_run)
    else:
        run_scheduler()


if __name__ == "__main__":
    main()
