# SPDX-License-Identifier: MPL-2.0

import json
from datetime import UTC, datetime

from cyberbrain.dreaming.audit import DreamRunAuditStore
from cyberbrain.dreaming.gate import DreamEvidenceGate, PromotionDecision
from cyberbrain.dreaming.promotion import DreamPromotionCoordinator
from cyberbrain.dreaming.reasoner import (
    DreamCandidate,
    DreamReasoningRequest,
    DreamReasoningResult,
    EvidenceItem,
)


def _request() -> DreamReasoningRequest:
    now = datetime(2026, 9, 4, 2, 0, tzinfo=UTC)
    evidence = [
        EvidenceItem(
            id="e1",
            record_type="knowledge",
            content="tested",
            score=0.9,
            event_time=now,
            metadata={"verification": "tested"},
        ),
        EvidenceItem(
            id="e2",
            record_type="episode",
            content="observed",
            score=0.9,
            event_time=now,
            metadata={"verification": "observed"},
        ),
        EvidenceItem(
            id="e3",
            record_type="knowledge",
            content="confirmed",
            score=0.9,
            event_time=now,
            metadata={"verification": "user_confirmed"},
        ),
    ]
    return DreamReasoningRequest(
        request_id="req-audit",
        session_id="session-audit",
        focal_topics=["topic"],
        session_start=now,
        session_end=now,
        evidence_by_topic={"topic": evidence},
    )


def _result() -> DreamReasoningResult:
    return DreamReasoningResult(
        request_id="req-audit",
        candidates=[
            DreamCandidate(
                entity_name="durable_lesson",
                entity_type="lesson",
                summary="summary",
                content="durable claim",
                evidence_ids=["e1", "e2", "e3"],
                confidence=0.92,
                classification="new_knowledge",
            )
        ],
    )


def test_promotion_coordinator_audits_gate_decision(tmp_path) -> None:
    store = DreamRunAuditStore(tmp_path / "dreaming.sqlite")
    coordinator = DreamPromotionCoordinator(
        gate=DreamEvidenceGate(),
        audit_store=store,
    )

    evaluation = coordinator.evaluate(
        request=_request(),
        result=_result(),
        dream_run_id="dream-run-1",
    )

    assert evaluation.dream_run.status == "evaluated"
    assert evaluation.dream_run.input_evidence_ids == ["e1", "e2", "e3"]
    assert evaluation.gate.candidates[0].decision == PromotionDecision.PROMOTE

    rows = store.decisions("dream-run-1")
    assert len(rows) == 1
    assert rows[0]["decision"] == "promote"
    assert json.loads(rows[0]["evidence_ids_json"]) == ["e1", "e2", "e3"]
    candidate = json.loads(rows[0]["candidate_json"])
    assert candidate["content"] == "durable claim"
