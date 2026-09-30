# SPDX-License-Identifier: MPL-2.0
"""Opt-in scheduler heartbeat; freshness is distinct from successful enqueue."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def write_heartbeat(path: str | Path, *, phase: str, next_run: datetime,
                    last_success: datetime | None = None, error: str | None = None,
                    now: datetime | None = None) -> None:
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None or next_run.tzinfo is None:
        raise ValueError("heartbeat times must include a timezone")
    if phase not in {"waiting", "running", "error"}:
        raise ValueError("unknown heartbeat phase")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": phase, "updated_at": instant.isoformat(),
        "next_run": next_run.isoformat(),
        "last_success": last_success.isoformat() if last_success else None,
        "error_type": error,
    }
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle)
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def heartbeat_status(path: str | Path, *, now: datetime | None = None,
                     max_age_seconds: float = 180, max_run_seconds: float = 900) -> dict:
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None or max_age_seconds <= 0 or max_run_seconds <= 0:
        raise ValueError("invalid heartbeat clock or limits")
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        updated = datetime.fromisoformat(payload["updated_at"])
        due = datetime.fromisoformat(payload["next_run"])
        if updated.tzinfo is None or due.tzinfo is None:
            raise ValueError("missing timezone")
        age = (instant - updated).total_seconds()
        phase = payload["phase"]
        freshness_limit = max_run_seconds if phase == "running" else max_age_seconds
        healthy = (
            phase in {"waiting", "running"} and not payload.get("error_type")
            and 0 <= age <= freshness_limit
            and (phase != "waiting" or due >= instant)
        )
        return {
            "healthy": healthy, "phase": phase,
            "age_seconds": max(0, round(age, 3)),
            "has_completed_run": bool(payload.get("last_success")),
        }
    except (OSError, ValueError, TypeError, KeyError):
        return {"healthy": False, "phase": "unavailable", "has_completed_run": False}
