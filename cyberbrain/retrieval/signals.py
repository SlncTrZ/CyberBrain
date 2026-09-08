# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import RetrievalHit


@dataclass(frozen=True, slots=True)
class ScopeTemporalSignals:
    project_bonus: float = 0.01
    topic_bonus: float = 0.005
    entity_bonus: float = 0.005
    active_bonus: float = 0.003

    def contributions(
        self,
        hit: RetrievalHit,
        *,
        project: str | None = None,
        topic: str | None = None,
        entity_name: str | None = None,
        status: str | None = None,
        not_after: datetime | None = None,
    ) -> tuple[bool, dict[str, float]]:
        if project is not None and hit.project is not None and hit.project != project:
            return False, {"project_mismatch": -1.0}
        if status is not None and hit.status is not None and hit.status != status:
            return False, {"status_mismatch": -1.0}
        if not_after is not None and hit.event_time is not None and hit.event_time > not_after:
            return False, {"future_ineligible": -1.0}

        result: dict[str, float] = {}
        if project is not None and hit.project == project:
            result["project_match"] = self.project_bonus
        if topic is not None and hit.topic == topic:
            result["topic_match"] = self.topic_bonus
        if entity_name is not None and hit.entity_name == entity_name:
            result["entity_match"] = self.entity_bonus
        if hit.status == "active":
            result["active_status"] = self.active_bonus
        return True, result
