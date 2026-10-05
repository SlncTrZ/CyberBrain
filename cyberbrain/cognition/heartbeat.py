# SPDX-License-Identifier: MPL-2.0
"""Deterministic bounded cognitive executive loop and scheduler.

This heartbeat is bounded open-work inspection, eligibility selection, and
idempotent auditing. It is explicitly NOT a periodic free-form LLM inner monologue.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from cyberbrain.cognition.calibration import MetacognitionCalibrationService
from cyberbrain.cognition.prediction import PredictionLearningService


class CognitiveHeartbeat:
    """Deterministic executive loop over bounded cognitive pending work."""

    def __init__(
        self,
        *,
        prediction_learning: PredictionLearningService,
        calibration: MetacognitionCalibrationService,
        stale_threshold_hours: int = 24,
    ) -> None:
        self._prediction_learning = prediction_learning
        self._calibration = calibration
        self._stale_threshold_hours = stale_threshold_hours

    def run_once(
        self,
        *,
        dry_run: bool = False,
        scan_limit: int = 100,
        agent: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=self._stale_threshold_hours)

        pending_list = self._prediction_learning.pending(
            limit=scan_limit,
            agent=agent,
            session_id=session_id,
        )

        stale_count = 0
        correlation_ids: set[str] = set()
        duplicate_correlations = 0

        for item in pending_list.items:
            if item.event_time < cutoff:
                stale_count += 1
            if item.correlation_id:
                if item.correlation_id in correlation_ids:
                    duplicate_correlations += 1
                else:
                    correlation_ids.add(item.correlation_id)

        calibration_report = self._calibration.observe(
            agent=agent,
            limit=scan_limit,
        )

        eligible_jobs = pending_list.returned

        summary = {
            "event": "cognitive_heartbeat_summary",
            "run_at": now.isoformat(),
            "dry_run": dry_run,
            "pending_predictions": pending_list.returned,
            "stale_predictions": stale_count,
            "duplicate_correlations": duplicate_correlations,
            "calibration_samples": calibration_report.usable_samples,
            "calibration_assessment": calibration_report.assessment.value,
            "eligible_cognitive_jobs": eligible_jobs,
            "status": "ready" if eligible_jobs > 0 else "idle",
        }
        return summary
