# SPDX-License-Identifier: MPL-2.0
"""Prospective Prediction/Outcome Event Producer Seam.
Enables agents and automated workflows to record predictions before actions
and resolve them deterministically after observations.
Updated: 2026-10-24 12:30
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

from cyberbrain.cognition.calibration import MetacognitionCalibrationService
from cyberbrain.cognition.prediction import (
    PredictionAssessment,
    PredictionLearningService,
)
from cyberbrain.core.runtime import build_runtime
from cyberbrain.core.settings import Settings
from cyberbrain.schemas.models import EpisodeRecord, IdentityTrust
from cyberbrain.tenancy.durable import bind_job_authority


class PredictionHandle:
    def __init__(self, record: EpisodeRecord, prediction_service: PredictionLearningService):
        self.record = record
        self.prediction_id: UUID = record.id
        self._service = prediction_service
        self.resolved = False

    def resolve(
        self,
        *,
        observed_outcome: str,
        assessment: PredictionAssessment | str,
        event_time: datetime | None = None,
    ) -> EpisodeRecord:
        now = event_time or datetime.now(UTC)
        result = self._service.record_outcome(
            prediction_id=self.prediction_id,
            observed_outcome=observed_outcome,
            assessment=assessment,
            event_time=now,
        )
        self.resolved = True
        return result


@contextmanager
def track_prediction(
    prediction_service: PredictionLearningService,
    *,
    expected_outcome: str,
    confidence: float = 0.9,
    action: str | None = None,
    rationale: str | None = None,
    session_id: str = "agent_action_loop",
    agent: str | None = "coding-agents",
    project: str | None = "CyberBrain",
    topic: str | None = "cognition",
    strategy_tags: list[str] | None = None,
    identity_trust: IdentityTrust = IdentityTrust.UNSPECIFIED,
) -> Iterator[PredictionHandle]:
    """Context manager for prospective prediction tracking.

    Auto-resolves as CONTRADICTED if an unhandled exception occurs,
    or allows manual resolution within the block.
    """
    now = datetime.now(UTC)
    record = prediction_service.record_prediction(
        expected_outcome=expected_outcome,
        confidence=confidence,
        session_id=session_id,
        event_time=now,
        action=action,
        rationale=rationale,
        agent=agent,
        project=project,
        topic=topic,
        strategy_tags=strategy_tags or [],
        identity_trust=identity_trust,
    )
    handle = PredictionHandle(record, prediction_service)
    try:
        yield handle
    except Exception as exc:
        if not handle.resolved:
            handle.resolve(
                observed_outcome=f"Action failed with exception: {type(exc).__name__}: {exc}",
                assessment=PredictionAssessment.CONTRADICTED,
            )
        raise
    else:
        if not handle.resolved:
            handle.resolve(
                observed_outcome="Action completed successfully as expected",
                assessment=PredictionAssessment.CONFIRMED,
            )


def run_command_with_prediction(
    prediction_service: PredictionLearningService,
    *,
    command: list[str],
    action: str,
    expected_outcome: str,
    confidence: float,
    session_id: str,
    project: str,
    topic: str,
    timeout: float = 300.0,
) -> int:
    with track_prediction(
        prediction_service,
        expected_outcome=expected_outcome,
        confidence=confidence,
        action=action,
        session_id=session_id,
        project=project,
        topic=topic,
    ) as handle:
        print(
            f"[Prediction Recorded] ID={handle.prediction_id}: "
            f"{expected_outcome} (conf={confidence})"
        )
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired as exc:
            handle.resolve(
                observed_outcome=f"Process timed out after {timeout} seconds",
                assessment=PredictionAssessment.CONTRADICTED,
            )
            print(f"[Outcome Resolved] Assessment=CONTRADICTED (timed out after {timeout}s)")
            raise exc

        if result.returncode == 0:
            handle.resolve(
                observed_outcome=f"Process exited 0. Output length: {len(result.stdout)} chars",
                assessment=PredictionAssessment.CONFIRMED,
            )
            print("[Outcome Resolved] Assessment=CONFIRMED (exit 0)")
        else:
            err_msg = result.stderr[:300]
            handle.resolve(
                observed_outcome=f"Process failed with exit code {result.returncode}: {err_msg}",
                assessment=PredictionAssessment.CONTRADICTED,
            )
            print(f"[Outcome Resolved] Assessment=CONTRADICTED (exit {result.returncode})")
        return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    status_parser = subparsers.add_parser(
        "status", help="Check current prediction and calibration metrics"
    )
    status_parser.add_argument("--agent", default=None)
    status_parser.add_argument("--project", default=None)

    run_parser = subparsers.add_parser(
        "run", help="Run a command wrapped in prospective prediction/outcome seam"
    )
    run_parser.add_argument("--action", required=True, help="Description of action being attempted")
    run_parser.add_argument("--expected", required=True, help="Expected outcome of the action")
    run_parser.add_argument(
        "--confidence", type=float, default=0.9, help="Confidence in expected outcome (0.0 to 1.0)"
    )
    run_parser.add_argument("--session-id", default="cli_action_session")
    run_parser.add_argument("--project", default="CyberBrain")
    run_parser.add_argument("--topic", default="ops")
    run_parser.add_argument("cmd", nargs=argparse.REMAINDER, help="Command to execute")

    args = parser.parse_args()
    settings = Settings()
    services = build_runtime(settings)
    prediction_service = services.prediction_learning

    with bind_job_authority(None):
        if args.subcommand == "status":
            summary = prediction_service.observe(agent=args.agent, project=args.project)
            cal_service = MetacognitionCalibrationService(prediction_learning=prediction_service)
            report = cal_service.observe(agent=args.agent, project=args.project)
            print("\n=== Prediction Summary ===")
            for k, v in summary.model_dump().items():
                print(f"  {k}: {v}")
            print("\n=== Calibration Report ===")
            for k, v in report.model_dump().items():
                print(f"  {k}: {v}")
        elif args.subcommand == "run":
            if not args.cmd:
                print("Error: No command specified to run.", file=sys.stderr)
                sys.exit(1)
            # Remove leading '--' if present
            cmd = args.cmd[1:] if args.cmd[0] == "--" else args.cmd
            exit_code = run_command_with_prediction(
                prediction_service,
                command=cmd,
                action=args.action,
                expected_outcome=args.expected,
                confidence=args.confidence,
                session_id=args.session_id,
                project=args.project,
                topic=args.topic,
            )
            sys.exit(exit_code)


if __name__ == "__main__":
    main()
