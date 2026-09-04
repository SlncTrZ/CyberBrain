# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

from cyberbrain.dreaming.audit import DreamRunAuditStore
from cyberbrain.dreaming.gate import CandidateGateResult, PromotionDecision
from cyberbrain.dreaming.queue import DreamQueue
from cyberbrain.dreaming.reasoner import DreamCandidate, DreamReasoningRequest, EvidenceItem
from cyberbrain.dreaming.writeback import DreamKnowledgeWriter, DreamWriteStatus


class DreamOperations:
    def __init__(
        self,
        *,
        queue: DreamQueue,
        audit: DreamRunAuditStore,
        writer: DreamKnowledgeWriter | None = None,
    ) -> None:
        self._queue = queue
        self._audit = audit
        self._writer = writer

    def enqueue(self, *, session_id: str, topics: list[str]) -> dict:
        value = session_id.strip()
        if not value:
            raise ValueError("session_id must not be empty")
        normalized_topics = self._normalize_topics(topics)
        return asdict(self._queue.enqueue(value, normalized_topics))

    def status(self, *, session_id: str) -> dict:
        return asdict(self._queue.get_by_session(session_id.strip()))

    def pending_reviews(self, *, limit: int = 100) -> list[dict]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        rows = self._audit.pending_reviews(limit=limit)
        return [self._normalize_review_row(row) for row in rows]

    def review(
        self,
        *,
        dream_run_id: str,
        candidate_index: int,
        resolution: str,
        reviewer: str,
        reason: str | None = None,
    ) -> dict:
        existing = self._audit.review_resolution(dream_run_id, candidate_index)
        if existing is None:
            self._audit.resolve_review(
                dream_run_id=dream_run_id,
                candidate_index=candidate_index,
                resolution=resolution,
                reviewer=reviewer,
                reason=reason,
            )
        elif existing["resolution"] != resolution:
            raise ValueError("review candidate is already resolved differently")

        resolved = self._audit.review_resolution(dream_run_id, candidate_index)
        if resolved is None:
            raise RuntimeError("review resolution was not persisted")
        response = dict(resolved)
        if resolution != "approved":
            return response

        prior_write = self._audit.write(dream_run_id, candidate_index)
        if (
            prior_write is not None
            and prior_write.get("write_status") == DreamWriteStatus.WRITTEN.value
        ):
            response["write"] = prior_write
            return response
        if self._writer is None:
            raise RuntimeError("Dream review writeback is not configured")

        decision_row = self._audit.decision(dream_run_id, candidate_index)
        if decision_row["decision"] != PromotionDecision.REVIEW.value:
            raise ValueError("manual approval requires an original review decision")
        candidate = DreamCandidate(**json.loads(str(decision_row["candidate_json"])))
        request = self._request_from_snapshot(self._audit.request_snapshot(dream_run_id))
        decision = CandidateGateResult(
            candidate_index=candidate_index,
            decision=PromotionDecision.PROMOTE,
            reasoner_confidence=float(decision_row["reasoner_confidence"]),
            evidence_strength=float(decision_row["evidence_strength"]),
            promotion_confidence=float(decision_row["promotion_confidence"]),
            evidence_ids=list(json.loads(str(decision_row["evidence_ids_json"]))),
            reasons=[*json.loads(str(decision_row["reasons_json"])), "manual_review_approved"],
        )
        write = self._writer.write_candidate(
            request=request,
            candidate=candidate,
            decision=decision,
            dream_run_id=dream_run_id,
            candidate_index=candidate_index,
        )
        evolution = write.evolution
        self._audit.record_write(
            dream_run_id=dream_run_id,
            candidate_index=candidate_index,
            write_status=write.status.value,
            write_reason=write.reason,
            evolution_outcome=evolution.outcome.value if evolution else None,
            knowledge_id=str(evolution.record.id) if evolution else None,
            previous_knowledge_id=(
                str(evolution.previous_id)
                if evolution and evolution.previous_id is not None
                else None
            ),
        )
        response["write"] = self._audit.write(dream_run_id, candidate_index)
        return response

    @staticmethod
    def _request_from_snapshot(snapshot: dict) -> DreamReasoningRequest:
        evidence_by_topic: dict[str, list[EvidenceItem]] = {}
        for topic, items in dict(snapshot["evidence_by_topic"]).items():
            evidence_by_topic[str(topic)] = [
                EvidenceItem(
                    id=str(item["id"]),
                    record_type=str(item["record_type"]),
                    content=str(item["content"]),
                    score=(float(item["score"]) if item.get("score") is not None else None),
                    event_time=(
                        datetime.fromisoformat(str(item["event_time"]).replace("Z", "+00:00"))
                        if item.get("event_time")
                        else None
                    ),
                    metadata=dict(item.get("metadata") or {}),
                )
                for item in items
            ]
        return DreamReasoningRequest(
            request_id=str(snapshot["request_id"]),
            session_id=str(snapshot["session_id"]),
            focal_topics=list(snapshot["focal_topics"]),
            session_start=datetime.fromisoformat(
                str(snapshot["session_start"]).replace("Z", "+00:00")
            ),
            session_end=datetime.fromisoformat(str(snapshot["session_end"]).replace("Z", "+00:00")),
            evidence_by_topic=evidence_by_topic,
            instructions_version=str(snapshot.get("instructions_version") or "1"),
        )

    @staticmethod
    def _normalize_topics(topics: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for topic in topics:
            value = str(topic).strip()
            normalized = value.casefold()
            if not value or normalized in seen:
                continue
            seen.add(normalized)
            result.append(value)
        return result

    @staticmethod
    def _normalize_review_row(row: dict) -> dict:
        result = dict(row)
        for key in ("candidate_json", "evidence_ids_json", "reasons_json"):
            value = result.get(key)
            if isinstance(value, str):
                result[key.removesuffix("_json")] = json.loads(value)
                del result[key]
        return result
