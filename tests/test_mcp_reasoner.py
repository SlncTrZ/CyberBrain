# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime

from cyberbrain.dreaming.adapters.mcp_reasoner import MCPReasoner
from cyberbrain.dreaming.reasoner import DreamReasoningRequest, EvidenceItem


class FakeInvoker:
    def __init__(self) -> None:
        self.tool: str | None = None
        self.arguments: dict | None = None

    def invoke(self, *, tool: str, arguments: dict):
        self.tool = tool
        self.arguments = arguments
        return {
            "request_id": arguments["request_id"],
            "candidates": [
                {
                    "entity_name": "provider_boundary",
                    "entity_type": "decision",
                    "summary": "Reasoner remains transport-agnostic.",
                    "content": "CyberBrain core does not know model or transport details.",
                    "evidence_ids": ["e1"],
                    "confidence": 0.98,
                    "classification": "new_knowledge",
                    "negative_knowledge": False,
                    "context": {"transport": "mcp-first"},
                }
            ],
            "notes": ["validated"],
        }


def test_mcp_reasoner_maps_canonical_contract_without_model_metadata() -> None:
    invoker = FakeInvoker()
    reasoner = MCPReasoner(invoker=invoker, tool="reasoner.reason")
    request = DreamReasoningRequest(
        request_id="req-1",
        session_id="session-1",
        focal_topics=["CyberBrain"],
        session_start=datetime(2026, 9, 4, 1, 0, tzinfo=UTC),
        session_end=datetime(2026, 9, 4, 2, 0, tzinfo=UTC),
        evidence_by_topic={
            "CyberBrain": [
                EvidenceItem(
                    id="e1",
                    record_type="episode",
                    content="Use an open Reasoner boundary.",
                    score=0.9,
                    event_time=datetime(2026, 9, 4, 1, 30, tzinfo=UTC),
                )
            ]
        },
    )

    result = reasoner.reason(request)

    assert invoker.tool == "reasoner.reason"
    assert "model" not in invoker.arguments
    assert "provider" not in invoker.arguments
    assert result.request_id == "req-1"
    assert result.candidates[0].context == {"transport": "mcp-first"}
