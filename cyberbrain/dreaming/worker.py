# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Protocol

from cyberbrain.core.metrics import MetricsRegistry
from cyberbrain.dreaming.engine import DreamingEngine
from cyberbrain.dreaming.planner import EpisodeSnippet
from cyberbrain.dreaming.promotion import DreamPromotionCoordinator
from cyberbrain.dreaming.queue import DreamJob, DreamQueue
from cyberbrain.dreaming.writeback import DreamWritebackCoordinator, DreamWriteResult
from cyberbrain.schemas.models import DreamStatus


class SessionEpisodeLoader(Protocol):
    def load(self, session_id: str) -> list[EpisodeSnippet]: ...

    def update_status(
        self,
        session_id: str,
        *,
        status: DreamStatus,
        dream_run_id: str | None = None,
        dreamed_at: datetime | None = None,
    ) -> int: ...


@dataclass(frozen=True)
class DreamWorkerResult:
    job_id: int
    session_id: str
    status: str
    dream_run_id: str | None
    writes: list[DreamWriteResult]
    error: str | None = None


class DreamWorker:
    def __init__(
        self,
        *,
        queue: DreamQueue,
        session_loader: SessionEpisodeLoader,
        engine: DreamingEngine,
        promotion: DreamPromotionCoordinator,
        writeback: DreamWritebackCoordinator,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._queue = queue
        self._session_loader = session_loader
        self._engine = engine
        self._promotion = promotion
        self._writeback = writeback
        self._metrics = metrics

    def process_next(self) -> DreamWorkerResult | None:
        job = self._queue.claim_next()
        if job is None:
            return None
        return self.process_job(job)

    def process_job(self, job: DreamJob) -> DreamWorkerResult:
        if job.status != "processing":
            raise ValueError("Dream job must be claimed before processing")
        started = monotonic()
        if self._metrics is not None:
            self._metrics.increment("dream_jobs_started_total")
        dream_run_id: str | None = None
        try:
            episodes = self._session_loader.load(job.session_id)
            dry_run = self._engine.dry_run(
                episodes,
                session_id=job.session_id,
                focal_topics=job.topics or None,
            )
            evaluation = self._promotion.evaluate(
                request=dry_run.request,
                result=dry_run.result,
            )
            dream_run_id = evaluation.dream_run.id
            writes = self._writeback.write_and_audit(
                request=dry_run.request,
                result=dry_run.result,
                gate=evaluation.gate,
                dream_run_id=dream_run_id,
            )
            self._session_loader.update_status(
                job.session_id,
                status=DreamStatus.PROCESSED,
                dream_run_id=dream_run_id,
                dreamed_at=datetime.now(UTC),
            )
            self._queue.mark_processed(job.id)
            if self._metrics is not None:
                self._metrics.increment("dream_jobs_processed_total")
                self._metrics.increment("dream_write_results_total", len(writes))
                self._metrics.observe("dream_job_seconds", monotonic() - started)
            return DreamWorkerResult(
                job_id=job.id,
                session_id=job.session_id,
                status="processed",
                dream_run_id=dream_run_id,
                writes=writes,
            )
        except Exception as exc:
            try:
                self._session_loader.update_status(
                    job.session_id,
                    status=DreamStatus.FAILED,
                    dream_run_id=dream_run_id,
                )
            except Exception:
                pass
            self._queue.mark_failed(job.id, str(exc))
            if self._metrics is not None:
                self._metrics.increment("dream_jobs_failed_total")
                self._metrics.observe("dream_job_seconds", monotonic() - started)
            return DreamWorkerResult(
                job_id=job.id,
                session_id=job.session_id,
                status="failed",
                dream_run_id=dream_run_id,
                writes=[],
                error=str(exc),
            )
