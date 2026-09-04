# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime, timedelta

import pytest

from cyberbrain.dreaming.orchestration import MultipassDreamReasoner
from cyberbrain.dreaming.reasoner import (
    DreamReasoningRequest,
    EvidenceItem,
    ReasoningClaim,
    ReasoningTaskKind,
    ReasoningTaskResult,
)


class FakeMicroReasoner:
    def reason_task(self, task):  # noqa: ANN001
        prefix = {
            ReasoningTaskKind.CURRENT_STATE: "Current fact",
            ReasoningTaskKind.SUPERSEDED_OR_REMOVED: "Removed fact",
            ReasoningTaskKind.DURABLE_LESSON: "Durable lesson",
            ReasoningTaskKind.CAVEAT: "Explicit caveat",
        }[task.kind]
        return ReasoningTaskResult(
            task_id=task.task_id,
            claims=[
                ReasoningClaim(
                    claim=f"{prefix}: {task.topic}",
                    evidence_ids=[item.id for item in task.evidence],
                    confidence=0.9,
                )
            ],
        )


class FabricatingMicroReasoner:
    def reason_task(self, task):  # noqa: ANN001
        return ReasoningTaskResult(
            task_id=task.task_id,
            claims=[ReasoningClaim(claim="bad", evidence_ids=["fabricated"], confidence=0.9)],
        )


def _request() -> DreamReasoningRequest:
    now = datetime(2026, 9, 4, 2, 0, tzinfo=UTC)
    return DreamReasoningRequest(
        request_id="req-1",
        session_id="session-1",
        focal_topics=["slnc_video_adapter"],
        session_start=now - timedelta(hours=1),
        session_end=now,
        evidence_by_topic={
            "slnc_video_adapter": [
                EvidenceItem(
                    id="e1",
                    record_type="knowledge",
                    content="LLM decides parameters; script executes deterministically.",
                    score=0.9,
                    event_time=now - timedelta(days=3),
                ),
                EvidenceItem(
                    id="e2",
                    record_type="knowledge",
                    content="Validation depends on production_mode and runs before generation.",
                    score=0.92,
                    event_time=now - timedelta(days=2),
                ),
                EvidenceItem(
                    id="e3",
                    record_type="knowledge",
                    content="OpenMontage removed and replaced by internal stack.",
                    score=0.95,
                    event_time=now - timedelta(days=1),
                ),
                EvidenceItem(
                    id="e4",
                    record_type="knowledge",
                    content="Lưu ý: validate --strict failed old images; not a regression.",
                    score=0.8,
                    event_time=now,
                ),
            ]
        },
    )


def test_multipass_reasoner_builds_grounded_candidates() -> None:
    result = MultipassDreamReasoner(micro_reasoner=FakeMicroReasoner()).reason(_request())

    assert result.request_id == "req-1"
    assert result.candidates
    assert any(candidate.classification == "rejected_approach" for candidate in result.candidates)
    assert any(candidate.entity_type == "lesson" for candidate in result.candidates)
    assert all(candidate.evidence_ids for candidate in result.candidates)
    assert result.notes == ["multipass_tasks=6"]


def test_multipass_reasoner_rejects_fabricated_evidence() -> None:
    with pytest.raises(ValueError, match="fabricated evidence IDs"):
        MultipassDreamReasoner(micro_reasoner=FabricatingMicroReasoner()).reason(_request())


def test_single_evidence_does_not_duplicate_current_or_infer_lesson() -> None:
    now = datetime(2026, 9, 4, 2, 0, tzinfo=UTC)
    request = DreamReasoningRequest(
        request_id="req-single",
        session_id="session-single",
        focal_topics=["single"],
        session_start=now,
        session_end=now,
        evidence_by_topic={
            "single": [
                EvidenceItem(
                    id="e1",
                    record_type="episode",
                    content="One isolated observation.",
                    score=0.7,
                    event_time=now,
                )
            ]
        },
    )

    result = MultipassDreamReasoner(micro_reasoner=FakeMicroReasoner()).reason(request)

    assert result.notes == ["multipass_tasks=1"]
    assert len(result.candidates) == 1
    assert result.candidates[0].context["reasoning_section"] == "current_state"
