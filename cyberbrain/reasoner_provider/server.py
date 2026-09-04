# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import mcp.types as types
from mcp.server import Server
from pydantic import ValidationError

from cyberbrain.reasoner_provider.backend import MicroReasoningBackend, ReasoningBackend
from cyberbrain.reasoner_provider.contracts import (
    ReasonRequest,
    ReasonResult,
    ReasonTaskRequest,
    ReasonTaskResult,
    validate_result_against_request,
    validate_task_result,
)

PROVIDER_NAME = "reasoner"
PROVIDER_VERSION = "0.1.0"
CONTRACT_VERSION = "1"

server = Server(PROVIDER_NAME)
_backend: ReasoningBackend | None = None
_micro_backend: MicroReasoningBackend | None = None


def configure_backend(backend: ReasoningBackend) -> None:
    global _backend
    _backend = backend


def configure_micro_backend(backend: MicroReasoningBackend) -> None:
    global _micro_backend
    _micro_backend = backend


def _require_backend() -> ReasoningBackend:
    if _backend is None:
        raise RuntimeError("Reasoner backend is not configured")
    return _backend


def _require_micro_backend() -> MicroReasoningBackend:
    if _micro_backend is None:
        raise RuntimeError("Micro Reasoner backend is not configured")
    return _micro_backend


def _guide_path() -> Path:
    return Path(__file__).resolve().parents[2] / "specs" / "REASONER_MCP_PROVIDER.md"


def _help_text() -> str:
    guide = _guide_path().read_text(encoding="utf-8")
    digest = hashlib.sha256(guide.encode("utf-8")).hexdigest()
    return (
        f"provider_name: {PROVIDER_NAME}\n"
        f"provider_version: {PROVIDER_VERSION}\n"
        f"contract_version: {CONTRACT_VERSION}\n"
        f"contract_hash: {digest}\n"
        f"capabilities: reasoning, micro-reasoning\n\n"
        f"{guide}"
    )


def _error(kind: str, message: str) -> list[types.TextContent]:
    return [
        types.TextContent(
            type="text",
            text=json.dumps({"error": {"type": kind, "message": message}}, ensure_ascii=False),
        )
    ]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="help",
            description="Return the current Reasoner provider contract and guide.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        types.Tool(
            name="reason",
            description=(
                "Produce evidence-backed Dreaming candidates without writing CyberBrain data."
            ),
            inputSchema=ReasonRequest.model_json_schema(),
        ),
        types.Tool(
            name="reason_task",
            description=(
                "Resolve one bounded evidence-grounded micro reasoning task for multipass Dreaming."
            ),
            inputSchema=ReasonTaskRequest.model_json_schema(),
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    if name == "help":
        return [types.TextContent(type="text", text=_help_text())]
    if name == "reason":
        return _call_reason(arguments or {})
    if name == "reason_task":
        return _call_reason_task(arguments or {})
    return _error("not_found", f"Unknown tool: {name}")


def _call_reason(arguments: dict) -> list[types.TextContent]:
    try:
        request = ReasonRequest.model_validate(arguments)
    except ValidationError as exc:
        return _error("validation_error", str(exc))

    try:
        raw_result = _require_backend().reason(request.model_dump(mode="json"))
        result = ReasonResult.model_validate(raw_result)
        validate_result_against_request(request, result)
    except (ValidationError, ValueError) as exc:
        return _error("validation_error", str(exc))
    except Exception as exc:
        return _error("internal_error", str(exc))

    return [types.TextContent(type="text", text=result.model_dump_json())]


def _call_reason_task(arguments: dict) -> list[types.TextContent]:
    try:
        request = ReasonTaskRequest.model_validate(arguments)
    except ValidationError as exc:
        return _error("validation_error", str(exc))

    try:
        raw_result = _require_micro_backend().reason_task(request.model_dump(mode="json"))
        result = ReasonTaskResult.model_validate(raw_result)
        validate_task_result(request, result)
    except (ValidationError, ValueError) as exc:
        return _error("validation_error", str(exc))
    except Exception as exc:
        return _error("internal_error", str(exc))

    return [types.TextContent(type="text", text=result.model_dump_json())]


@server.list_prompts()
async def list_prompts() -> list[types.Prompt]:
    return []


@server.list_resources()
async def list_resources() -> list[types.Resource]:
    return []
