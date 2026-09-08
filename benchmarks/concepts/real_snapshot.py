# SPDX-License-Identifier: MPL-2.0
"""Read-only M4 benchmark over a Knowledge/Episodic JSONL snapshot."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from benchmarks.evidence.corpus_census import (
    ConceptEvidenceEligibility,
    classify_row,
)
from cyberbrain.concepts import (
    ConceptDiscoveryEngine,
    ConceptEvidence,
    ConceptEvidenceType,
    ConceptPromotionGate,
    ConceptShadowRegistry,
)

Mode = Literal["strict", "reviewed_historical"]


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"row {line_number} must be an object")
        rows.append(value)
    return rows


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("payload")
    return dict(value) if isinstance(value, dict) else dict(row)


def _scope_marker(payload: dict[str, Any]) -> str:
    project = str(payload.get("project") or "").strip()
    return f"snapshot:single-owner:{project or 'global'}"


def _reviewed_historical_eligible(row: dict[str, Any]) -> bool:
    classification = classify_row(row)
    if classification.eligibility is not ConceptEvidenceEligibility.REVIEW_ONLY:
        return False
    reasons = set(classification.reasons)
    return reasons == {"migrated_provenance"}


def _selected(row: dict[str, Any], mode: Mode) -> bool:
    classification = classify_row(row)
    if classification.eligibility is ConceptEvidenceEligibility.ELIGIBLE_SHADOW:
        return True
    return mode == "reviewed_historical" and _reviewed_historical_eligible(row)


def _concept_evidence(row: dict[str, Any]) -> ConceptEvidence:
    payload = _payload(row)
    record_type = str(payload.get("record_type") or row.get("kind") or "")
    if record_type == "knowledge":
        evidence_type = ConceptEvidenceType.KNOWLEDGE
    elif record_type == "episode":
        evidence_type = ConceptEvidenceType.EPISODE
    else:
        raise ValueError(f"unsupported record_type for concept benchmark: {record_type!r}")
    return ConceptEvidence(
        evidence_id=str(payload.get("id") or row.get("id") or ""),
        record_type=evidence_type,
        scope_marker=_scope_marker(payload),
        domain=str(payload.get("domain") or "episodic"),
        topic=str(payload.get("topic") or ""),
        project=payload.get("project"),
        entity_type=payload.get("entity_type"),
        entity_name=payload.get("entity_name"),
        session_id=payload.get("session_id"),
        source=payload.get("source"),
        verification=payload.get("verification"),
        counterexample=bool(payload.get("negative_knowledge", False)),
    )


def _review_key(scope_marker: str, domain: str, topic: str) -> tuple[str, str, str]:
    return (scope_marker.strip(), domain.strip().casefold(), topic.strip().casefold())


def _load_reviews(path: Path | None) -> dict[tuple[str, str, str], str]:
    if path is None:
        return {}
    root = json.loads(path.read_text(encoding="utf-8"))
    rows = root.get("reviews") if isinstance(root, dict) else None
    if not isinstance(rows, list):
        raise ValueError("concept review manifest must contain a reviews list")
    allowed = {"useful_concept", "false_abstraction", "uncertain"}
    reviews: dict[tuple[str, str, str], str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("concept review row must be an object")
        disposition = str(row.get("disposition") or "")
        if disposition not in allowed:
            raise ValueError(f"invalid concept review disposition: {disposition!r}")
        key = _review_key(
            str(row.get("scope_marker") or ""),
            str(row.get("domain") or ""),
            str(row.get("topic") or ""),
        )
        if key in reviews:
            raise ValueError(f"duplicate concept review key: {key!r}")
        reviews[key] = disposition
    return reviews


def run(
    *,
    snapshot_path: Path,
    mode: Mode = "strict",
    review_manifest: Path | None = None,
) -> dict[str, Any]:
    if mode not in {"strict", "reviewed_historical"}:
        raise ValueError(f"unsupported concept benchmark mode: {mode!r}")

    rows = _load_jsonl(snapshot_path)
    selected_rows = [row for row in rows if _selected(row, mode)]
    evidence = [_concept_evidence(row) for row in selected_rows]
    candidates = ConceptDiscoveryEngine().discover(evidence)

    registry = ConceptShadowRegistry()
    first_registry = registry.observe(candidates)
    second_registry = registry.observe(candidates)

    gate = ConceptPromotionGate()
    promotion_counts = Counter(gate.evaluate(candidate).decision.value for candidate in candidates)
    reviews = _load_reviews(review_manifest)
    reviewed_counts: Counter[str] = Counter()
    unreviewed_candidate_count = 0
    per_candidate: list[dict[str, Any]] = []
    for candidate in candidates:
        key = _review_key(candidate.scope_marker, candidate.domain, candidate.topic)
        disposition = reviews.get(key)
        if disposition is None:
            unreviewed_candidate_count += 1
        else:
            reviewed_counts[disposition] += 1
        promotion = gate.evaluate(candidate)
        per_candidate.append(
            {
                "candidate_concept_id": candidate.candidate_concept_id,
                "scope_marker": candidate.scope_marker,
                "domain": candidate.domain,
                "topic": candidate.topic,
                "support_count": len(candidate.supporting_evidence_ids),
                "counterexample_count": len(candidate.counterexample_ids),
                "distinct_entity_count": candidate.distinct_entity_count,
                "distinct_session_count": candidate.distinct_session_count,
                "distinct_source_count": candidate.distinct_source_count,
                "strong_verification_count": candidate.strong_verification_count,
                "formation_confidence": candidate.formation_confidence,
                "review_disposition": disposition,
                "promotion_decision": promotion.decision.value,
                "promotion_reasons": list(promotion.reasons),
            }
        )

    reviewed_binary = reviewed_counts["useful_concept"] + reviewed_counts["false_abstraction"]
    precision = (
        reviewed_counts["useful_concept"] / reviewed_binary if reviewed_binary else None
    )
    false_abstraction_rate = (
        reviewed_counts["false_abstraction"] / reviewed_binary if reviewed_binary else None
    )
    candidate_review_keys = {
        _review_key(candidate.scope_marker, candidate.domain, candidate.topic)
        for candidate in candidates
    }
    expected_useful_keys = {
        key for key, disposition in reviews.items() if disposition == "useful_concept"
    }
    detected_useful_count = len(candidate_review_keys & expected_useful_keys)
    useful_recall = (
        detected_useful_count / len(expected_useful_keys) if expected_useful_keys else None
    )
    suppressed_reviewed_count = len(set(reviews) - candidate_review_keys)
    candidate_ids = [candidate.candidate_concept_id for candidate in candidates]
    return {
        "source": str(snapshot_path),
        "mode": mode,
        "snapshot_rows": len(rows),
        "selected_evidence_rows": len(evidence),
        "candidate_count": len(candidates),
        "duplicate_candidate_rate": (
            1 - len(set(candidate_ids)) / len(candidate_ids) if candidate_ids else 0.0
        ),
        "registry": {
            "first_added": first_registry.added_count,
            "second_stable": second_registry.stable_count,
            "second_changed": second_registry.changed_count,
            "stability_rate": (
                second_registry.stable_count / len(candidates) if candidates else 1.0
            ),
        },
        "promotion_decisions": dict(sorted(promotion_counts.items())),
        "reviewed": {
            "counts": dict(sorted(reviewed_counts.items())),
            "reviewed_binary_count": reviewed_binary,
            "precision": precision,
            "false_abstraction_rate": false_abstraction_rate,
            "expected_useful_count": len(expected_useful_keys),
            "detected_useful_count": detected_useful_count,
            "useful_recall": useful_recall,
            "suppressed_reviewed_count": suppressed_reviewed_count,
            "unreviewed_candidate_count": unreviewed_candidate_count,
        },
        "per_candidate": sorted(
            per_candidate,
            key=lambda row: (-int(row["support_count"]), str(row["candidate_concept_id"])),
        ),
        "changes_runtime_behavior": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="M4 read-only concept snapshot benchmark")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument(
        "--mode",
        choices=("strict", "reviewed_historical"),
        default="strict",
    )
    parser.add_argument("--review-manifest", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                snapshot_path=args.snapshot,
                mode=args.mode,
                review_manifest=args.review_manifest,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
