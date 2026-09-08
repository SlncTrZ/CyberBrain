# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class RetrievalIntent(StrEnum):
    CURRENT_FACT = "current_fact"
    HISTORICAL_EVENT = "historical_event"
    TIMELINE = "timeline"
    PROJECT_SCOPED = "project_scoped"
    TEMPORAL = "temporal"


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    id: str
    text: str = ""
    score: float | None = None
    project: str | None = None
    topic: str | None = None
    entity_name: str | None = None
    status: str | None = None
    event_time: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RankedHit:
    id: str
    score: float
    contributions: dict[str, float] = field(default_factory=dict)
