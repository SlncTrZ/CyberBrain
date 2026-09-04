# SPDX-License-Identifier: MPL-2.0

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from cyberbrain.knowledge.evolution import EvolutionOutcome, EvolutionResult
from cyberbrain.mcp.server import call_tool, configure_dream_operations, configure_runtime
from cyberbrain.schemas.models import EpisodeRecord, KnowledgeRecord


class FakeKnowledgeSearch:
    def search(self, **kwargs):
        return [{"id": "k1", "score": 0.9, "content": "ok", **kwargs}]

    def timeline(self, **kwargs):
        return [{"id": "k1", "version": 1, **kwargs}]


class FakeKnowledgeEvolution:
    def store(self, **kwargs):
        record = KnowledgeRecord(
            content=kwargs["content"],
            domain=kwargs["domain"],
            topic=kwargs["topic"],
            entity_type=kwargs["entity_type"],
            entity_name=kwargs["entity_name"],
            content_hash="0" * 64,
        )
        return EvolutionResult(EvolutionOutcome.INSERT_NEW, record)


class FakeDreamOperations:
    def enqueue(self, **kwargs):
        return {"status": "pending", **kwargs}

    def status(self, **kwargs):
        return {"status": "processed", **kwargs}

    def pending_reviews(self, **kwargs):
        return [{"dream_run_id": "run-1", "candidate_index": 0, **kwargs}]

    def review(self, **kwargs):
        return kwargs


class FakeMemory:
    def search(self, **kwargs):
        return [{"id": "e1", "score": 0.8, **kwargs}]

    def store(self, **kwargs):
        return EpisodeRecord(
            id=uuid4(),
            content=kwargs["content"],
            session_id=kwargs["session_id"],
            event_time=kwargs["event_time"],
            content_hash="1" * 64,
        )


@dataclass
class FakeRuntime:
    knowledge_evolution: FakeKnowledgeEvolution
    knowledge_search: FakeKnowledgeSearch
    memory: FakeMemory


def setup_module() -> None:
    configure_runtime(FakeRuntime(FakeKnowledgeEvolution(), FakeKnowledgeSearch(), FakeMemory()))
    configure_dream_operations(FakeDreamOperations())


def _call(name: str, args: dict) -> dict | list:
    result = asyncio.run(call_tool(name, args))
    return json.loads(result[0].text)


def test_knowledge_search_handler() -> None:
    result = _call("knowledge_search", {"query": "x", "domain": "ops", "limit": 3})
    assert result[0]["query"] == "x"
    assert result[0]["domain"] == "ops"
    assert result[0]["limit"] == 3


def test_knowledge_store_handler() -> None:
    result = _call(
        "knowledge_store",
        {
            "content": "Use authenticated MCP.",
            "domain": "ops",
            "topic": "mcp",
            "entity_type": "decision",
            "entity_name": "auth",
        },
    )
    assert result["outcome"] == "insert_new"
    assert result["record"]["entity_name"] == "auth"


def test_memory_store_handler_parses_datetime() -> None:
    result = _call(
        "memory_store",
        {
            "content": "session note",
            "session_id": "s1",
            "event_time": datetime.now(UTC).isoformat(),
        },
    )
    assert result["session_id"] == "s1"


def test_memory_search_handler_applies_filters() -> None:
    result = _call("memory_search", {"query": "x", "channel": "chatgpt", "limit": 2})
    assert result[0]["channel"] == "chatgpt"
    assert result[0]["limit"] == 2


def test_legacy_knowledge_search_maps_wing_to_domain() -> None:
    result = _call("knowledge_search", {"query": "x", "wing": "tcdserver", "limit": 3})
    assert result[0]["domain"] == "ops"
    assert result[0]["query"] == "x"


def test_ai_memory_read_combines_knowledge_and_memory() -> None:
    result = _call("ai_memory_read", {"query": "remember"})
    assert result["knowledge"][0]["query"] == "remember"
    assert result["memory"][0]["query"] == "remember"


def test_conversation_recall_maps_to_memory_search() -> None:
    result = _call(
        "conversation_recall",
        {"query": "hello", "channel": "telegram", "limit": 4},
    )
    assert result[0]["query"] == "hello"
    assert result[0]["channel"] == "telegram"
    assert result[0]["limit"] == 4


def test_dream_enqueue_handler() -> None:
    result = _call(
        "dream_enqueue",
        {"session_id": "session-1", "topics": ["CyberBrain", "MCP"]},
    )
    assert result["status"] == "pending"
    assert result["session_id"] == "session-1"
    assert result["topics"] == ["CyberBrain", "MCP"]


def test_dream_status_handler() -> None:
    result = _call("dream_status", {"session_id": "session-1"})
    assert result == {"status": "processed", "session_id": "session-1"}


def test_dream_reviews_handler() -> None:
    result = _call("dream_reviews", {"limit": 10})
    assert result == [{"dream_run_id": "run-1", "candidate_index": 0, "limit": 10}]


def test_dream_review_resolve_handler() -> None:
    result = _call(
        "dream_review_resolve",
        {
            "dream_run_id": "run-1",
            "candidate_index": 0,
            "resolution": "approved",
            "reviewer": "human:test",
            "reason": "checked",
        },
    )
    assert result["resolution"] == "approved"
    assert result["reviewer"] == "human:test"


def test_unknown_tool_returns_stable_not_found_error() -> None:
    result = _call("does_not_exist", {})
    assert result == {
        "error": {
            "type": "not_found",
            "message": "Unknown tool: does_not_exist",
            "retryable": False,
        }
    }


def test_invalid_tool_arguments_return_validation_error() -> None:
    result = _call(
        "memory_store",
        {
            "content": "session note",
            "session_id": "s1",
            "event_time": "not-a-date",
        },
    )
    assert result["error"]["type"] == "validation_error"
    assert result["error"]["retryable"] is False


def test_tool_handler_does_not_mutate_input_arguments() -> None:
    args = {"query": "x", "domain": "ops", "limit": 3}
    original = dict(args)

    _call("knowledge_search", args)

    assert args == original
