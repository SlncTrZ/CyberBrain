# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from scripts.rescue_blocked_candidates import parse_request_snapshot


def test_parse_request_snapshot():
    now = datetime.now(UTC)
    snapshot = {
        "request_id": "req-1",
        "session_id": "sess-1",
        "focal_topics": ["topic_a"],
        "session_start": now.isoformat(),
        "session_end": now.isoformat(),
        "evidence_by_topic": {
            "topic_a": [
                {
                    "id": str(uuid4()),
                    "record_type": "episode",
                    "content": "test episode",
                    "score": 0.9,
                    "event_time": now.isoformat(),
                    "metadata": {"project": "CyberBrain"},
                }
            ]
        },
    }
    parsed = parse_request_snapshot(snapshot)
    assert parsed.request_id == "req-1"
    assert parsed.session_id == "sess-1"
    assert len(parsed.evidence_by_topic["topic_a"]) == 1
    assert parsed.evidence_by_topic["topic_a"][0].content == "test episode"
