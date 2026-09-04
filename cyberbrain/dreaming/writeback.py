# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from cyberbrain.dreaming.audit import DreamRunAuditStore
from cyberbrain.dreaming.gate import CandidateGateResult, DreamGateResult, PromotionDecision
from cyberbrain.dreaming.reasoner import (
    DreamCandidate,
    DreamReasoningRequest,
    DreamReasoningResult,
    EvidenceItem,
)
from cyberbrain.knowledge.evolution import EvolutionResult, KnowledgeEvolutionService
from cyberbrain.schemas.models import Origin, Verification


class DreamWriteStatus(StrEnum):
    WRITTEN = "written"
    SKIPPED_NOT_PROMOTED = "skipped_not_promoted"
    BLOCKED_METADATA = "blocked_metadata"
    BLOCKED_EVIDENCE_ID = "blocked_evidence_id"


@dataclass(frozen=True)
class DreamWriteResult:
    candidate_index: int
    status: DreamWriteStatus
    reason: str
    evolution: EvolutionResult | None = None


class DreamWritebackCoordinator:
    def __init__(
        self,
        *,
        writer: DreamKnowledgeWriter,
        audit_store: DreamRunAuditStore,
    ) -> None:
        self._writer = writer
        self._audit_store = audit_store

    def write_and_audit(
        self,
        *,
        request: DreamReasoningRequest,
        result: DreamReasoningResult,
        gate: DreamGateResult,
        dream_run_id: str,
    ) -> list[DreamWriteResult]:
        writes = self._writer.write_promoted(
            request=request,
            result=result,
            gate=gate,
            dream_run_id=dream_run_id,
        )
        for write in writes:
            evolution = write.evolution
            self._audit_store.record_write(
                dream_run_id=dream_run_id,
                candidate_index=write.candidate_index,
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
        return writes


class DreamKnowledgeWriter:
    """Writes only already-promoted Dream candidates through Knowledge Evolution."""

    def __init__(self, evolution: KnowledgeEvolutionService) -> None:
        self._evolution = evolution

    def write_promoted(
        self,
        *,
        request: DreamReasoningRequest,
        result: DreamReasoningResult,
        gate: DreamGateResult,
        dream_run_id: str,
    ) -> list[DreamWriteResult]:
        if result.request_id != request.request_id or gate.request_id != request.request_id:
            raise ValueError("request/result/gate request_id mismatch")

        evidence_by_id = {
            item.id: item
            for items in request.evidence_by_topic.values()
            for item in items
        }

        writes: list[DreamWriteResult] = []
        for decision in gate.candidates:
            index = decision.candidate_index
            if index < 0 or index >= len(result.candidates):
                raise ValueError("gate candidate index is out of range")
            candidate = result.candidates[index]
            writes.append(
                self.write_candidate(
                    request=request,
                    candidate=candidate,
                    decision=decision,
                    dream_run_id=dream_run_id,
                    candidate_index=index,
                    evidence_by_id=evidence_by_id,
                )
            )
        return writes

    def write_candidate(
        self,
        *,
        request: DreamReasoningRequest,
        candidate: DreamCandidate,
        decision: CandidateGateResult,
        dream_run_id: str,
        candidate_index: int,
        evidence_by_id: dict[str, EvidenceItem] | None = None,
    ) -> DreamWriteResult:
        if decision.decision != PromotionDecision.PROMOTE:
            return DreamWriteResult(
                candidate_index=candidate_index,
                status=DreamWriteStatus.SKIPPED_NOT_PROMOTED,
                reason=f"gate_decision={decision.decision.value}",
            )

        lookup = evidence_by_id or {
            item.id: item
            for items in request.evidence_by_topic.values()
            for item in items
        }
        try:
            selected = [lookup[evidence_id] for evidence_id in candidate.evidence_ids]
        except KeyError:
            return DreamWriteResult(
                candidate_index=candidate_index,
                status=DreamWriteStatus.BLOCKED_EVIDENCE_ID,
                reason="candidate references evidence outside Dream request snapshot",
            )
        try:
            evidence_ids = [UUID(item.id) for item in selected]
        except ValueError:
            return DreamWriteResult(
                candidate_index=candidate_index,
                status=DreamWriteStatus.BLOCKED_EVIDENCE_ID,
                reason="canonical Knowledge evidence_ids must be UUID point IDs",
            )

        domain = self._single_metadata_value(selected, "domain")
        if domain is None:
            return DreamWriteResult(
                candidate_index=candidate_index,
                status=DreamWriteStatus.BLOCKED_METADATA,
                reason="missing_or_ambiguous_domain",
            )

        project = self._single_metadata_value(selected, "project", allow_missing=True)
        verification = self._verification_for(selected)
        topic = self._topic_for(candidate, request, selected)
        context = dict(candidate.context)
        context.pop("reasoning_section", None)
        context.pop("task_id", None)

        evolution = self._evolution.store(
            content=candidate.content,
            summary=candidate.summary,
            domain=domain,
            topic=topic,
            entity_type=candidate.entity_type,
            entity_name=candidate.entity_name,
            project=project,
            change_reason="promoted from Dreaming evidence gate",
            verification=verification,
            confidence=decision.promotion_confidence,
            provenance_type="dream",
            source=f"dream_run:{dream_run_id}",
            evidence_ids=evidence_ids,
            origin=Origin.DREAM,
            dream_run_id=dream_run_id,
            negative_knowledge=candidate.negative_knowledge,
            context=context,
            extensions={
                "reasoner_confidence": decision.reasoner_confidence,
                "evidence_strength": decision.evidence_strength,
                "promotion_confidence": decision.promotion_confidence,
                "dream_classification": candidate.classification,
            },
        )
        return DreamWriteResult(
            candidate_index=candidate_index,
            status=DreamWriteStatus.WRITTEN,
            reason=evolution.outcome.value,
            evolution=evolution,
        )

    @staticmethod
    def _single_metadata_value(
        evidence: list[EvidenceItem],
        key: str,
        *,
        allow_missing: bool = False,
    ) -> str | None:
        values = {
            str(item.metadata[key]).strip()
            for item in evidence
            if item.metadata.get(key) is not None and str(item.metadata[key]).strip()
        }
        if len(values) == 1:
            return next(iter(values))
        if not values and allow_missing:
            return None
        return None

    @staticmethod
    def _verification_for(evidence: list[EvidenceItem]) -> Verification:
        values = {
            str(item.metadata.get("verification") or "").strip().casefold()
            for item in evidence
        }
        if Verification.USER_CONFIRMED.value in values:
            return Verification.USER_CONFIRMED
        if Verification.TESTED.value in values:
            return Verification.TESTED
        if Verification.OBSERVED.value in values:
            return Verification.OBSERVED
        return Verification.DERIVED

    @staticmethod
    def _topic_for(
        candidate: DreamCandidate,
        request: DreamReasoningRequest,
        evidence: list[EvidenceItem],
    ) -> str:
        topics = {
            str(item.metadata.get("topic") or "").strip()
            for item in evidence
            if str(item.metadata.get("topic") or "").strip()
        }
        if len(topics) == 1:
            return next(iter(topics))

        task_topic = str(candidate.context.get("topic") or "").strip()
        if task_topic:
            return task_topic

        if len(request.focal_topics) == 1:
            return request.focal_topics[0]

        raise ValueError("unable to resolve canonical topic for Dream candidate")
