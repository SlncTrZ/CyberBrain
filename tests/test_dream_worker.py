# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime

from cyberbrain.dreaming.audit import DreamRunAuditStore
from cyberbrain.dreaming.engine import DreamDryRunResult
from cyberbrain.dreaming.gate import DreamEvidenceGate
from cyberbrain.dreaming.planner import EpisodeSnippet
from cyberbrain.dreaming.promotion import DreamPromotionCoordinator
from cyberbrain.dreaming.queue import DreamQueue
from cyberbrain.dreaming.reasoner import (
    DreamCandidate,
    DreamReasoningRequest,
    DreamReasoningResult,
    EvidenceItem,
)
from cyberbrain.dreaming.worker import DreamWorker


class FakeSessionLoader:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.status_updates = []

    def load(self, session_id: str) -> list[EpisodeSnippet]:
        if self.fail:
            raise RuntimeError("session load failed")
        return [
            EpisodeSnippet(
                content="CyberBrain dreaming session",
                event_time=datetime(2026, 9, 4, 1, 0, tzinfo=UTC),
            )
        ]

    def update_status(self, session_id: str, **kwargs) -> int:  # noqa: ANN003
        self.status_updates.append((session_id, kwargs))
        return 1


class FakeEngine:
    def __init__(self) -> None:
        self.focal_topics: list[str] | None = None

    def dry_run(
        self,
        episodes: list[EpisodeSnippet],
        *,
        session_id: str,
        topic_limit: int = 3,
        focal_topics: list[str] | None = None,
    ) -> DreamDryRunResult:
        self.focal_topics = focal_topics
        now = datetime(2026, 9, 4, 1, 0, tzinfo=UTC)
        request = DreamReasoningRequest(
            request_id="req-worker",
            session_id=session_id,
            focal_topics=focal_topics or ["CyberBrain"],
            session_start=now,
            session_end=now,
            evidence_by_topic={
                (focal_topics or ["CyberBrain"])[0]: [
                    EvidenceItem(
                        id="11111111-1111-4111-8111-111111111111",
                        record_type="knowledge",
                        content="weak evidence",
                        score=0.8,
                        event_time=now,
                        metadata={"verification": "unverified"},
                    )
                ]
            },
        )
        result = DreamReasoningResult(
            request_id=request.request_id,
            candidates=[
                DreamCandidate(
                    entity_name="worker_lesson",
                    entity_type="lesson",
                    summary="summary",
                    content="candidate",
                    evidence_ids=["11111111-1111-4111-8111-111111111111"],
                    confidence=0.7,
                    classification="new_knowledge",
                )
            ],
        )
        return DreamDryRunResult(request=request, result=result)


class FakeWriteback:
    def __init__(self) -> None:
        self.calls = 0

    def write_and_audit(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls += 1
        return []


def test_worker_processes_job_and_uses_queued_topics(tmp_path) -> None:
    queue = DreamQueue(tmp_path / "queue.sqlite")
    queue.enqueue("session-1", ["CyberBrain"])
    audit = DreamRunAuditStore(tmp_path / "audit.sqlite")
    engine = FakeEngine()
    writeback = FakeWriteback()
    loader = FakeSessionLoader()
    worker = DreamWorker(
        queue=queue,
        session_loader=loader,
        engine=engine,
        promotion=DreamPromotionCoordinator(
            gate=DreamEvidenceGate(),
            audit_store=audit,
        ),
        writeback=writeback,
    )

    result = worker.process_next()

    assert result is not None
    assert result.status == "processed"
    assert result.dream_run_id is not None
    assert engine.focal_topics == ["CyberBrain"]
    assert writeback.calls == 1
    job = queue.get_by_session("session-1")
    assert job.status == "processed"
    assert job.attempt_count == 1
    assert len(loader.status_updates) == 1
    session_id, update = loader.status_updates[0]
    assert session_id == "session-1"
    assert update["status"].value == "processed"
    assert update["dream_run_id"] == result.dream_run_id
    assert update["dreamed_at"].tzinfo is not None


def test_worker_marks_job_failed_without_killing_queue(tmp_path) -> None:
    queue = DreamQueue(tmp_path / "queue.sqlite")
    queue.enqueue("session-1", ["CyberBrain"])
    audit = DreamRunAuditStore(tmp_path / "audit.sqlite")
    loader = FakeSessionLoader(fail=True)
    worker = DreamWorker(
        queue=queue,
        session_loader=loader,
        engine=FakeEngine(),
        promotion=DreamPromotionCoordinator(
            gate=DreamEvidenceGate(),
            audit_store=audit,
        ),
        writeback=FakeWriteback(),
    )

    result = worker.process_next()

    assert result is not None
    assert result.status == "failed"
    assert "session load failed" in (result.error or "")
    job = queue.get_by_session("session-1")
    assert job.status == "failed"
    assert job.attempt_count == 1
    assert job.last_error == "session load failed"
    assert len(loader.status_updates) == 1
    assert loader.status_updates[0][1]["status"].value == "failed"
