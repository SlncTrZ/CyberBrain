# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta

import httpx

from cyberbrain.dreaming.adapters.mcp_transport import MCPStreamableHTTPInvoker

BASE_URL = os.environ.get("CYBERBRAIN_IT_URL", "http://127.0.0.1:18767")
TOKEN = os.environ.get("CYBERBRAIN_IT_TOKEN", "integration-mcp-token")


def call(inv, tool, args):
    return inv.invoke(tool=tool, arguments=args)


def main():
    r = httpx.get(f"{BASE_URL}/health", timeout=10)
    r.raise_for_status()
    assert r.json()["provider"] == "cyberbrain"
    assert httpx.get(f"{BASE_URL}/metrics", timeout=10).status_code == 401
    headers = {"Authorization": f"Bearer {TOKEN}"}
    r = httpx.get(f"{BASE_URL}/metrics", headers=headers, timeout=10)
    r.raise_for_status()
    inv = MCPStreamableHTTPInvoker(url=f"{BASE_URL}/mcp", bearer_token=TOKEN, timeout_seconds=120)
    topic = "clean_host_integration"
    seed = [
        (
            "execution_boundary",
            "The model selects semantic parameters while deterministic code performs "
            "file and timeline operations.",
        ),
        (
            "validation_boundary",
            "Validation runs before generation and mode-specific rules are explicit.",
        ),
        (
            "provenance_boundary",
            "Dreaming conclusions must cite exact evidence point IDs before Knowledge writeback.",
        ),
    ]
    for name, content in seed:
        out = call(
            inv,
            "knowledge_store",
            {
                "content": content,
                "domain": "architecture",
                "topic": topic,
                "entity_type": "decision",
                "entity_name": name,
                "project": "CyberBrain",
                "verification": "tested",
                "origin": "ingestion",
                "source": "clean-host-integration",
            },
        )
        assert out["outcome"] in {"insert_new", "no_change", "evolve"}
    now = datetime.now(UTC)
    session = f"clean-host-{int(now.timestamp())}"
    episodes = [
        "The clean-host session confirms deterministic execution and provenance boundaries.",
        "The integration session completed after validation of the CyberBrain runtime.",
    ]
    for i, content in enumerate(episodes):
        out = call(
            inv,
            "memory_store",
            {
                "content": content,
                "session_id": session,
                "event_time": (now + timedelta(seconds=i + 1)).isoformat(),
                "project": "CyberBrain",
                "topic": topic,
                "source": "clean-host-integration",
            },
        )
        assert out["session_id"] == session
    call(inv, "dream_enqueue", {"session_id": session, "topics": [topic]})
    status = None
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        status = call(inv, "dream_status", {"session_id": session})
        if status["status"] in {"processed", "failed"}:
            break
        time.sleep(0.5)
    assert status and status["status"] == "processed", status
    reviews = call(inv, "dream_reviews", {"limit": 100})
    if reviews:
        selected = max(reviews, key=lambda x: float(x.get("evidence_strength", 0.0)))
        approval = call(
            inv,
            "dream_review_resolve",
            {
                "dream_run_id": selected["dream_run_id"],
                "candidate_index": int(selected["candidate_index"]),
                "resolution": "approved",
                "reviewer": "integration:clean-host",
                "reason": "automated clean-host lifecycle verification",
            },
        )
        assert approval.get("write", {}).get("write_status") == "written", approval
    search = call(
        inv,
        "knowledge_search",
        {"query": "deterministic execution provenance", "domain": "architecture", "limit": 10},
    )
    assert search
    metrics = httpx.get(f"{BASE_URL}/metrics", headers=headers, timeout=10).json()
    assert metrics["counters"].get("embedding_requests_total", 0) > 0
    assert metrics["counters"].get("qdrant_requests_total", 0) > 0
    print(
        json.dumps(
            {
                "health": "ok",
                "session_id": session,
                "dream_status": status["status"],
                "review_count": len(reviews),
                "search_results": len(search),
                "metrics": metrics,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
