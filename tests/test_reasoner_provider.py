# SPDX-License-Identifier: MPL-2.0

import asyncio
import json
from datetime import UTC, datetime

from cyberbrain.dreaming.adapters.mcp_micro_reasoner import MCPMicroReasoner
from cyberbrain.dreaming.adapters.mcp_reasoner import MCPReasoner
from cyberbrain.dreaming.orchestration import MultipassDreamReasoner
from cyberbrain.dreaming.reasoner import DreamReasoningRequest, EvidenceItem
from cyberbrain.reasoner_provider.server import (
    call_tool,
    configure_backend,
    configure_micro_backend,
    list_tools,
)


class DeterministicBackend:
    def reason(self, request: dict):
        first_topic = request["focal_topics"][0]
        first_evidence = request["evidence_by_topic"][first_topic][0]
        return {
            "request_id": request["request_id"],
            "candidates": [
                {
                    "entity_name": "open_reasoner_boundary",
                    "entity_type": "decision",
                    "summary": "Reasoner stays open and MCP-first.",
                    "content": "CyberBrain does not depend on a specific reasoning implementation.",
                    "evidence_ids": [first_evidence["id"]],
                    "confidence": 0.99,
                    "classification": "new_knowledge",
                    "negative_knowledge": False,
                    "context": {},
                }
            ],
            "notes": [],
        }


class DeterministicMicroBackend:
    def reason_task(self, request: dict):
        return {
            "task_id": request["task_id"],
            "claims": [
                {
                    "claim": f"Historical claim for {request['kind']}",
                    "evidence_ids": [item["id"] for item in request["evidence"]],
                    "confidence": 0.91,
                }
            ],
        }


class ProviderInvoker:
    def invoke(self, *, tool: str, arguments: dict):
        result = asyncio.run(call_tool(tool, arguments))
        payload = json.loads(result[0].text)
        if "error" in payload:
            raise RuntimeError(payload["error"])
        return payload


def setup_module() -> None:
    configure_backend(DeterministicBackend())
    configure_micro_backend(DeterministicMicroBackend())


def test_provider_exposes_reason_and_reason_task() -> None:
    tools = asyncio.run(list_tools())
    assert [tool.name for tool in tools] == ["help", "reason", "reason_task"]


def test_provider_rejects_unknown_evidence_id() -> None:
    class BadBackend:
        def reason(self, request: dict):
            return {
                "request_id": request["request_id"],
                "candidates": [
                    {
                        "entity_name": "bad",
                        "entity_type": "lesson",
                        "summary": "bad",
                        "content": "bad",
                        "evidence_ids": ["fabricated"],
                        "confidence": 0.5,
                        "classification": "new_knowledge",
                    }
                ],
                "notes": [],
            }

    configure_backend(BadBackend())
    result = asyncio.run(call_tool("reason", _request_payload()))
    payload = json.loads(result[0].text)
    assert payload["error"]["type"] == "validation_error"
    configure_backend(DeterministicBackend())


def test_provider_rejects_micro_reasoner_fabricated_evidence_id() -> None:
    class BadMicroBackend:
        def reason_task(self, request: dict):
            return {
                "task_id": request["task_id"],
                "claims": [
                    {
                        "claim": "bad",
                        "evidence_ids": ["fabricated"],
                        "confidence": 0.5,
                    }
                ],
            }

    configure_micro_backend(BadMicroBackend())
    result = asyncio.run(call_tool("reason_task", _task_payload()))
    payload = json.loads(result[0].text)
    assert payload["error"]["type"] == "validation_error"
    configure_micro_backend(DeterministicMicroBackend())


def test_cyberbrain_mcp_reasoner_round_trip() -> None:
    reasoner = MCPReasoner(invoker=ProviderInvoker(), tool="reason")
    request = _reasoning_request()

    result = reasoner.reason(request)
    assert result.request_id == request.request_id
    assert result.candidates[0].evidence_ids == ["evidence-1"]
    assert result.candidates[0].classification == "new_knowledge"


def test_multipass_mcp_micro_reasoner_round_trip() -> None:
    micro = MCPMicroReasoner(invoker=ProviderInvoker(), tool="reason_task")
    reasoner = MultipassDreamReasoner(micro_reasoner=micro)

    result = reasoner.reason(_reasoning_request())

    assert result.request_id == "req-roundtrip"
    assert result.candidates
    assert all(candidate.evidence_ids for candidate in result.candidates)
    assert all(candidate.context["task_id"] for candidate in result.candidates)


def _reasoning_request() -> DreamReasoningRequest:
    return DreamReasoningRequest(
        request_id="req-roundtrip",
        session_id="session-1",
        focal_topics=["CyberBrain"],
        session_start=datetime(2026, 9, 4, 1, 0, tzinfo=UTC),
        session_end=datetime(2026, 9, 4, 2, 0, tzinfo=UTC),
        evidence_by_topic={
            "CyberBrain": [
                EvidenceItem(
                    id="evidence-1",
                    record_type="episode",
                    content=(
                        "OpenMontage removed. LLM decides parameters; script executes. "
                        "Lưu ý: validate caveat remains."
                    ),
                    score=0.97,
                    event_time=datetime(2026, 9, 4, 1, 30, tzinfo=UTC),
                )
            ]
        },
    )


def _request_payload() -> dict:
    return {
        "request_id": "req-1",
        "session_id": "session-1",
        "focal_topics": ["CyberBrain"],
        "session_start": "2026-09-04T01:00:00Z",
        "session_end": "2026-09-04T02:00:00Z",
        "instructions_version": "1",
        "evidence_by_topic": {
            "CyberBrain": [
                {
                    "id": "evidence-1",
                    "record_type": "episode",
                    "content": "Evidence",
                    "score": 0.9,
                    "event_time": "2026-09-04T01:30:00Z",
                    "metadata": {},
                }
            ]
        },
    }


def _task_payload() -> dict:
    return {
        "task_id": "req-1:1:current_state",
        "request_id": "req-1",
        "topic": "CyberBrain",
        "kind": "current_state",
        "instruction": "Extract one current supported fact.",
        "evidence": [
            {
                "id": "evidence-1",
                "record_type": "episode",
                "content": "Evidence",
                "score": 0.9,
                "event_time": "2026-09-04T01:30:00Z",
                "metadata": {},
            }
        ],
    }
