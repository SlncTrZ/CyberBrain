# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import mcp.types as types
from mcp.server import Server

from cyberbrain import __version__
from cyberbrain.core.error_model import classify_error, not_found
from cyberbrain.core.errors import ConfigurationError
from cyberbrain.core.runtime import RuntimeServices
from cyberbrain.dreaming.operations import DreamOperations
from cyberbrain.schemas.models import EpisodeRole, Origin, Verification

PROVIDER_NAME = "cyberbrain"
CONTRACT_VERSION = "1"
SCHEMA_VERSION = "1"

server = Server(PROVIDER_NAME)
_runtime: RuntimeServices | None = None
_dream_operations: DreamOperations | None = None


def configure_runtime(runtime: RuntimeServices) -> None:
    global _runtime
    _runtime = runtime


def configure_dream_operations(operations: DreamOperations) -> None:
    global _dream_operations
    _dream_operations = operations


def _require_runtime() -> RuntimeServices:
    if _runtime is None:
        raise ConfigurationError("CyberBrain runtime services are not configured")
    return _runtime


def _require_dream_operations() -> DreamOperations:
    if _dream_operations is None:
        raise ConfigurationError("CyberBrain Dreaming operations are not configured")
    return _dream_operations


def _guide_path() -> Path:
    return Path(__file__).resolve().parents[2] / "TOOL_GUIDE.md"


def _legacy_domain(value: str) -> str:
    normalized = value.strip().casefold()
    mapping = {
        "code_chronicles": "code",
        "tcdserver": "ops",
        "openclaw": "ops",
        "robotics": "hardware",
        "omniscience_wiki": "research",
    }
    return mapping.get(normalized, normalized or "ops")


def _help_payload() -> str:
    guide = _guide_path().read_text(encoding="utf-8")
    contract_hash = hashlib.sha256(guide.encode("utf-8")).hexdigest()
    return (
        f"provider_name: {PROVIDER_NAME}\n"
        f"provider_version: {__version__}\n"
        f"protocol_version: mcp-streamable-http\n"
        f"contract_version: {CONTRACT_VERSION}\n"
        f"schema_version: {SCHEMA_VERSION}\n"
        f"contract_hash: {contract_hash}\n"
        f"authentication: Bearer token; optional X-API-Key compatibility\n"
        f"capabilities: knowledge, episodic-memory, dreaming\n\n"
        f"{guide}"
    )


def _json_text(value) -> list[types.TextContent]:  # noqa: ANN001
    return [types.TextContent(type="text", text=json.dumps(value, ensure_ascii=False, default=str))]


def _error_text(exc: Exception) -> list[types.TextContent]:
    return _json_text(classify_error(exc).as_dict())


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="help",
            description="Return the current CyberBrain provider contract and usage guide.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        types.Tool(
            name="knowledge_search",
            description="Semantic search over active canonical CyberBrain knowledge.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "domain": {"type": "string"},
                    "wing": {"type": "string"},
                    "topic": {"type": "string"},
                    "entity_type": {"type": "string"},
                    "entity_name": {"type": "string"},
                    "project": {"type": "string"},
                    "status": {"type": "string"},
                    "verification": {"type": "string"},
                    "origin": {"type": "string"},
                    "negative_knowledge": {"type": "boolean"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="knowledge_store",
            description="Store or evolve canonical CyberBrain knowledge.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "domain": {"type": "string"},
                    "wing": {"type": "string"},
                    "topic": {"type": "string"},
                    "entity_type": {"type": "string"},
                    "entity_name": {"type": "string"},
                    "summary": {"type": "string"},
                    "project": {"type": "string"},
                    "change_reason": {"type": "string"},
                    "importance": {"type": "string"},
                    "verification": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "provenance_type": {"type": "string"},
                    "source": {"type": "string"},
                    "origin": {"type": "string"},
                    "negative_knowledge": {"type": "boolean"},
                    "context": {"type": "object"},
                    "extensions": {"type": "object"},
                },
                "anyOf": [
                    {"required": ["content", "domain", "topic", "entity_type", "entity_name"]},
                    {"required": ["content", "wing", "topic"]},
                ],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="knowledge_timeline",
            description="Return version history for one canonical knowledge entity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "wing": {"type": "string"},
                    "topic": {"type": "string"},
                    "entity_type": {"type": "string"},
                    "entity_name": {"type": "string"},
                    "source_file": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                },
                "anyOf": [
                    {"required": ["domain", "topic", "entity_type", "entity_name"]},
                    {"required": ["wing"]},
                ],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="memory_search",
            description="Semantic search over canonical episodic memory with applied filters.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "session_id": {"type": "string"},
                    "channel": {"type": "string"},
                    "role": {"type": "string"},
                    "agent": {"type": "string"},
                    "project": {"type": "string"},
                    "topic": {"type": "string"},
                    "dream_status": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="memory_store",
            description="Store one canonical episodic memory record.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "session_id": {"type": "string"},
                    "event_time": {"type": "string", "format": "date-time"},
                    "channel": {"type": "string"},
                    "role": {"type": "string"},
                    "agent": {"type": "string"},
                    "project": {"type": "string"},
                    "topic": {"type": "string"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "importance": {"type": "string"},
                    "source": {"type": "string"},
                    "context": {"type": "object"},
                    "extensions": {"type": "object"},
                },
                "required": ["content", "session_id", "event_time"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="tech_store",
            description="Legacy compatibility alias for storing technical knowledge.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "action": {"type": "string"},
                    "subject": {"type": "string"},
                    "importance": {"type": "string"},
                },
                "required": ["content", "action", "subject"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="tech_find",
            description="Legacy compatibility alias for semantic knowledge search.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "wing": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="ai_memory_read",
            description="Legacy compatibility alias for combined Knowledge and Episodic recall.",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="conversation_save",
            description="Legacy compatibility alias for storing one conversation memory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "channel": {"type": "string"},
                    "session_id": {"type": "string"},
                    "role": {"type": "string"},
                    "importance": {"type": "string"},
                },
                "required": ["content", "channel"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="conversation_recall",
            description="Legacy compatibility alias for episodic semantic recall.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "channel": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="dream_enqueue",
            description="Queue one completed session for evidence-gated Dreaming.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "topics": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["session_id"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="dream_status",
            description="Return queue status for one Dreaming session.",
            inputSchema={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="dream_reviews",
            description="List unresolved Dreaming candidates requiring manual review.",
            inputSchema={
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 500}},
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="dream_review_resolve",
            description="Approve or reject one already-gated Dreaming review candidate.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dream_run_id": {"type": "string"},
                    "candidate_index": {"type": "integer", "minimum": 0},
                    "resolution": {"type": "string", "enum": ["approved", "rejected"]},
                    "reviewer": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["dream_run_id", "candidate_index", "resolution", "reviewer"],
                "additionalProperties": False,
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    if name == "help":
        return [types.TextContent(type="text", text=_help_payload())]
    try:
        return _dispatch_tool(name, dict(arguments or {}))
    except Exception as exc:
        return _error_text(exc)


def _dispatch_tool(name: str, args: dict) -> list[types.TextContent]:
    runtime = _require_runtime()

    if name == "knowledge_search":
        limit = int(args.pop("limit", 5))
        query = str(args.pop("query"))
        wing = args.pop("wing", None)
        if wing is not None:
            if str(wing).strip().casefold() == "conversation":
                return _json_text(
                    runtime.memory.search(
                        query=query,
                        limit=limit,
                        topic=args.pop("topic", None),
                    )
                )
            args.setdefault("domain", _legacy_domain(str(wing)))
        return _json_text(runtime.knowledge_search.search(query=query, limit=limit, **args))

    if name == "knowledge_store":
        verification = Verification(args.pop("verification", Verification.UNVERIFIED.value))
        origin = Origin(args.pop("origin", Origin.INGESTION.value))
        wing = args.pop("wing", None)
        if wing is not None and "domain" not in args:
            args["domain"] = _legacy_domain(str(wing))
            args.setdefault("entity_type", "concept")
            if not args.get("entity_name"):
                digest = hashlib.sha256(
                    str(args.get("content") or "").encode("utf-8")
                ).hexdigest()[:12]
                args["entity_name"] = f"legacy:{args.get('topic', 'general')}:{digest}"
        result = runtime.knowledge_evolution.store(
            verification=verification,
            origin=origin,
            **args,
        )
        return _json_text(
            {
                "outcome": result.outcome.value,
                "record": result.record.model_dump(mode="json"),
                "previous_id": result.previous_id,
            }
        )

    if name == "knowledge_timeline":
        wing = args.pop("wing", None)
        source_file = args.pop("source_file", None)
        if wing is None:
            return _json_text(runtime.knowledge_search.timeline(**args))
        conditions = [{"key": "domain", "match": {"value": _legacy_domain(str(wing))}}]
        if args.get("entity_name"):
            conditions.append({"key": "entity_name", "match": {"value": args["entity_name"]}})
        if source_file:
            conditions.append({"key": "source", "match": {"value": source_file}})
        points = runtime.repository.scroll(
            runtime.knowledge_search.collection,
            qdrant_filter={"must": conditions},
            limit=int(args.get("limit", 100)),
        )
        rows = [{"id": point["id"], **(point.get("payload") or {})} for point in points]
        rows.sort(key=lambda item: int(item.get("version", 0)), reverse=True)
        return _json_text(rows)

    if name == "memory_search":
        limit = int(args.pop("limit", 5))
        query = str(args.pop("query"))
        return _json_text(runtime.memory.search(query=query, limit=limit, **args))

    if name == "memory_store":
        event_time = datetime.fromisoformat(str(args.pop("event_time")).replace("Z", "+00:00"))
        role_value = args.pop("role", None)
        role = EpisodeRole(role_value) if role_value is not None else None
        record = runtime.memory.store(event_time=event_time, role=role, **args)
        return _json_text(record.model_dump(mode="json"))

    if name == "tech_store":
        content = str(args.pop("content"))
        action = str(args.pop("action"))
        subject = str(args.pop("subject"))
        importance = args.pop("importance", "medium")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
        result = runtime.knowledge_evolution.store(
            content=content,
            domain="ops",
            topic=action or "technical_note",
            entity_type="technical_note",
            entity_name=f"legacy:{action}:{subject}:{digest}",
            project=subject or None,
            importance=importance,
            change_reason=f"Stored via legacy tech_store: {action}",
            verification=Verification.UNVERIFIED,
            origin=Origin.INGESTION,
        )
        return _json_text(
            {
                "outcome": result.outcome.value,
                "record": result.record.model_dump(mode="json"),
                "previous_id": result.previous_id,
            }
        )

    if name == "tech_find":
        query = str(args.pop("query"))
        wing = args.pop("wing", None)
        filters = {"domain": _legacy_domain(str(wing))} if wing else {}
        return _json_text(runtime.knowledge_search.search(query=query, limit=5, **filters))

    if name == "ai_memory_read":
        query = str(args.pop("query"))
        return _json_text(
            {
                "knowledge": runtime.knowledge_search.search(query=query, limit=5),
                "memory": runtime.memory.search(query=query, limit=3),
            }
        )

    if name == "conversation_save":
        content = str(args.pop("content"))
        channel = str(args.pop("channel"))
        session_id = str(args.pop("session_id", "")).strip()
        if not session_id:
            session_id = f"legacy-mcp:{channel}:{int(datetime.now().timestamp() * 1000)}"
        role_value = args.pop("role", None)
        role = (
            EpisodeRole(role_value)
            if role_value in {item.value for item in EpisodeRole}
            else None
        )
        record = runtime.memory.store(
            content=content,
            session_id=session_id,
            event_time=datetime.now().astimezone(),
            channel=channel,
            role=role,
            importance=args.pop("importance", None),
            source="legacy_mcp_compat",
        )
        return _json_text(record.model_dump(mode="json"))

    if name == "conversation_recall":
        query = str(args.pop("query"))
        limit = int(args.pop("limit", 5))
        return _json_text(
            runtime.memory.search(
                query=query,
                limit=limit,
                channel=args.pop("channel", None),
            )
        )

    if name == "dream_enqueue":
        operations = _require_dream_operations()
        return _json_text(
            operations.enqueue(
                session_id=str(args.pop("session_id")),
                topics=list(args.pop("topics", [])),
            )
        )

    if name == "dream_status":
        operations = _require_dream_operations()
        return _json_text(operations.status(session_id=str(args.pop("session_id"))))

    if name == "dream_reviews":
        operations = _require_dream_operations()
        return _json_text(operations.pending_reviews(limit=int(args.pop("limit", 100))))

    if name == "dream_review_resolve":
        operations = _require_dream_operations()
        return _json_text(
            operations.review(
                dream_run_id=str(args.pop("dream_run_id")),
                candidate_index=int(args.pop("candidate_index")),
                resolution=str(args.pop("resolution")),
                reviewer=str(args.pop("reviewer")),
                reason=args.pop("reason", None),
            )
        )

    return _json_text(not_found(f"Unknown tool: {name}").as_dict())


@server.list_prompts()
async def list_prompts() -> list[types.Prompt]:
    return []


@server.list_resources()
async def list_resources() -> list[types.Resource]:
    return []
