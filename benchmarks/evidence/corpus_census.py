# SPDX-License-Identifier: MPL-2.0
"""Read-only E1 corpus census and concept-evidence eligibility analysis."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

_EVENT_MARKERS = (
    "action log",
    "commit ",
    "git status",
    "working tree",
    "deploy",
    "deployed",
    "restart",
    "restarted",
    "tests pass",
    "test pass",
    "ci run",
    "rollback",
)
_GENERIC_TOPICS = {"", "chat_history", "general", "legacy_source_chunk", "unknown"}


class ConceptEvidenceEligibility(StrEnum):
    ELIGIBLE_SHADOW = "eligible_shadow"
    REVIEW_ONLY = "review_only"
    EXCLUDED = "excluded"


@dataclass(frozen=True, slots=True)
class CensusClassification:
    record_id: str
    record_type: str
    active: bool
    research: bool
    legacy_chunk: bool
    migrated_provenance: bool
    mixed_operational: bool
    ambiguous: bool
    eligibility: ConceptEvidenceEligibility
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CorpusCensusReport:
    total_records: int
    record_type_counts: dict[str, int]
    active_knowledge: int
    research_records: int
    legacy_chunk_records: int
    migrated_provenance_records: int
    mixed_operational_records: int
    ambiguous_records: int
    concept_eligibility_counts: dict[str, int]
    historical_prediction_backfill_candidates: int


def _payload(row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if isinstance(row.get("payload"), dict):
        payload = dict(row["payload"])
        record_type = str(payload.get("record_type") or row.get("kind") or "unknown")
        return record_type, payload
    record_type = str(row.get("record_type") or row.get("kind") or "unknown")
    return record_type, dict(row)


def _text_for_marker_scan(payload: dict[str, Any]) -> str:
    summary = str(payload.get("summary") or "")
    content = str(payload.get("content") or "")
    return f"{summary}\n{content[:4000]}".casefold()


def classify_row(row: dict[str, Any]) -> CensusClassification:
    record_type, payload = _payload(row)
    record_id = str(payload.get("id") or row.get("id") or "").strip()
    status = str(payload.get("status") or "").strip().casefold()
    active = record_type == "episode" or status == "active"
    verification = str(payload.get("verification") or "").strip().casefold()
    entity_type = str(payload.get("entity_type") or "").strip().casefold()
    provenance = str(payload.get("provenance_type") or "").strip().casefold()
    source = str(payload.get("source") or "").strip().casefold()
    topic = str(payload.get("topic") or "").strip()

    research = (
        str(payload.get("domain") or "").strip().casefold() == "research"
        or verification == "research"
        or entity_type == "web_research"
        or source == "web_search"
    )
    legacy_chunk = entity_type == "legacy_chunk" or topic.casefold() == "legacy_source_chunk"
    migrated_provenance = (
        provenance == "legacy_qdrant"
        or str(payload.get("origin") or "").strip().casefold() == "migration"
    )
    mixed_operational = record_type == "knowledge" and any(
        marker in _text_for_marker_scan(payload) for marker in _EVENT_MARKERS
    )

    required_missing = False
    if record_type == "knowledge":
        required_missing = any(
            not str(payload.get(key) or "").strip()
            for key in ("domain", "topic", "entity_type", "entity_name")
        )
    elif record_type == "episode":
        required_missing = any(
            not str(payload.get(key) or "").strip() for key in ("session_id", "event_time")
        )
    else:
        required_missing = True

    ambiguous = required_missing or record_type not in {"knowledge", "episode"}
    reasons: list[str] = []
    if not active:
        reasons.append("inactive_knowledge")
    if research:
        reasons.append("research_evidence")
    if legacy_chunk:
        reasons.append("legacy_chunk")
    elif migrated_provenance:
        reasons.append("migrated_provenance")
    if mixed_operational:
        reasons.append("mixed_operational_knowledge")
    if ambiguous:
        reasons.append("ambiguous_metadata")
    if topic.casefold() in _GENERIC_TOPICS:
        reasons.append("generic_or_missing_topic")

    if not active or legacy_chunk or ambiguous or topic.casefold() in _GENERIC_TOPICS:
        eligibility = ConceptEvidenceEligibility.EXCLUDED
    elif research or mixed_operational or migrated_provenance:
        eligibility = ConceptEvidenceEligibility.REVIEW_ONLY
    else:
        eligibility = ConceptEvidenceEligibility.ELIGIBLE_SHADOW

    return CensusClassification(
        record_id=record_id,
        record_type=record_type,
        active=active,
        research=research,
        legacy_chunk=legacy_chunk,
        migrated_provenance=migrated_provenance,
        mixed_operational=mixed_operational,
        ambiguous=ambiguous,
        eligibility=eligibility,
        reasons=tuple(reasons),
    )


def census(rows: list[dict[str, Any]]) -> tuple[CorpusCensusReport, list[CensusClassification]]:
    classified = [classify_row(row) for row in rows]
    record_types = Counter(item.record_type for item in classified)
    eligibility = Counter(item.eligibility.value for item in classified)
    report = CorpusCensusReport(
        total_records=len(classified),
        record_type_counts=dict(sorted(record_types.items())),
        active_knowledge=sum(
            item.record_type == "knowledge" and item.active for item in classified
        ),
        research_records=sum(item.research for item in classified),
        legacy_chunk_records=sum(item.legacy_chunk for item in classified),
        migrated_provenance_records=sum(item.migrated_provenance for item in classified),
        mixed_operational_records=sum(item.mixed_operational for item in classified),
        ambiguous_records=sum(item.ambiguous for item in classified),
        concept_eligibility_counts=dict(sorted(eligibility.items())),
        # E1 never reconstructs historical Prediction evidence from content heuristics.
        historical_prediction_backfill_candidates=0,
    )
    return report, classified


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"JSONL row {line_number} must be an object")
        rows.append(value)
    return rows


def run(path: Path, *, include_classifications: bool = False) -> dict[str, Any]:
    report, classified = census(_load_jsonl(path))
    output: dict[str, Any] = {
        "source": str(path),
        "report": asdict(report),
        "rule": (
            "read-only E1 census; historical Prediction/Outcome pairs are never reconstructed "
            "from prose/content heuristics"
        ),
    }
    if include_classifications:
        output["classifications"] = [asdict(item) for item in classified]
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="CyberBrain E1 read-only corpus census")
    parser.add_argument("path", type=Path)
    parser.add_argument("--include-classifications", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.path, include_classifications=args.include_classifications),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
