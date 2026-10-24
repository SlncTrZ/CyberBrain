# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from cyberbrain.core.errors import ConfigurationError
from cyberbrain.dreaming.audit import DreamRunAuditStore
from cyberbrain.dreaming.gate import CandidateGateResult, DreamGateResult, PromotionDecision
from cyberbrain.dreaming.reasoner import (
    DreamCandidate,
    DreamReasoningRequest,
    DreamReasoningResult,
    EvidenceItem,
)
from cyberbrain.knowledge.evolution import EvolutionResult, KnowledgeEvolutionService
from cyberbrain.relations.admission import _partition_conditions
from cyberbrain.relations.models import (
    EntityRef,
    EvidenceRef,
    RelationBundle,
    RelationEdge,
    RelationKind,
    RelationStatus,
)
from cyberbrain.schemas.models import Origin, Verification
from cyberbrain.tenancy import OperationClass, current_authority


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

    def __init__(
        self,
        evolution: KnowledgeEvolutionService,
        *,
        default_domain: str | None = None,
        enable_relation_linking: bool = True,
    ) -> None:
        self._evolution = evolution
        self._default_domain = (
            default_domain.strip() if default_domain and default_domain.strip() else None
        )
        self._enable_relation_linking = enable_relation_linking

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
            item.id: item for items in request.evidence_by_topic.values() for item in items
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
        domain_override: str | None = None,
    ) -> DreamWriteResult:
        if decision.decision != PromotionDecision.PROMOTE:
            return DreamWriteResult(
                candidate_index=candidate_index,
                status=DreamWriteStatus.SKIPPED_NOT_PROMOTED,
                reason=f"gate_decision={decision.decision.value}",
            )

        lookup = evidence_by_id or {
            item.id: item for items in request.evidence_by_topic.values() for item in items
        }
        target_evidence_ids = decision.evidence_ids or candidate.evidence_ids
        try:
            selected = [lookup[evidence_id] for evidence_id in target_evidence_ids]
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

        domain = self._domain_for(
            candidate=candidate,
            request=request,
            evidence=selected,
            domain_override=domain_override,
        )
        if domain is None:
            return DreamWriteResult(
                candidate_index=candidate_index,
                status=DreamWriteStatus.BLOCKED_METADATA,
                reason="missing_or_ambiguous_domain",
            )

        attribution = {}
        for key in ("tenant", "user", "agent", "project"):
            concrete_values = {
                str(item.metadata[key]).strip()
                for item in selected
                if item.metadata.get(key) is not None and str(item.metadata[key]).strip()
            }
            if len(concrete_values) > 1:
                return DreamWriteResult(
                    candidate_index=candidate_index,
                    status=DreamWriteStatus.BLOCKED_METADATA,
                    reason=f"mixed_identity_{key}",
                )
            attribution[key] = next(iter(concrete_values), None)
        verification = self._verification_for(selected)
        topic = self._topic_for(candidate, request, selected)
        context = dict(candidate.context)
        context.pop("reasoning_section", None)
        context.pop("task_id", None)

        extensions_dict = {
            "reasoner_confidence": decision.reasoner_confidence,
            "evidence_strength": decision.evidence_strength,
            "promotion_confidence": decision.promotion_confidence,
            "dream_classification": candidate.classification,
        }
        if self._enable_relation_linking:
            try:
                source_ref = EntityRef.from_payload({
                    "domain": domain,
                    "topic": topic,
                    "entity_type": candidate.entity_type,
                    "entity_name": candidate.entity_name,
                    **attribution,
                })
                bundle = self._build_candidate_relations(
                    source_ref=source_ref,
                    candidate=candidate,
                    topic=topic,
                    evidence_ids=evidence_ids,
                )
                if bundle is not None and bundle.edges:
                    extensions_dict["relations"] = bundle.model_dump(mode="json")
            except Exception:
                pass

        try:
            evolution = self._evolution.store(
                content=candidate.content,
                summary=candidate.summary,
                domain=domain,
                topic=topic,
                entity_type=candidate.entity_type,
                entity_name=candidate.entity_name,
                **attribution,
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
                extensions=extensions_dict,
            )
        except ConfigurationError:
            # Fall back to clean store without relations if admission failed
            extensions_dict.pop("relations", None)
            evolution = self._evolution.store(
                content=candidate.content,
                summary=candidate.summary,
                domain=domain,
                topic=topic,
                entity_type=candidate.entity_type,
                entity_name=candidate.entity_name,
                **attribution,
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
                extensions=extensions_dict,
            )

        return DreamWriteResult(
            candidate_index=candidate_index,
            status=DreamWriteStatus.WRITTEN,
            reason=evolution.outcome.value,
            evolution=evolution,
        )

    def _build_candidate_relations(
        self,
        *,
        source_ref: EntityRef,
        candidate: DreamCandidate,
        topic: str,
        evidence_ids: list[UUID],
    ) -> RelationBundle | None:
        try:
            lookup_text = f"{topic} {candidate.entity_name} {candidate.summary[:100]}".strip()
            vector = self._evolution._embedding.embed(lookup_text)
            partition_conds = _partition_conditions(source_ref.scope, include_session=True)
            search_filter = {
                "must": [
                    *partition_conds,
                    {"key": "status", "match": {"value": "active"}},
                    {"key": "record_type", "match": {"value": "knowledge"}},
                    {"key": "record_class", "match": {"value": "knowledge"}},
                ]
            }
            matches = self._evolution._repository.search(
                self._evolution._collection,
                vector=vector,
                limit=3,
                score_threshold=0.75,
                qdrant_filter=search_filter,
            )
            authority = current_authority()
            has_admin_review = (
                authority is not None
                and OperationClass.ADMIN_REVIEW in authority.grant.operations
            )
            status = RelationStatus.ACCEPTED if has_admin_review else RelationStatus.PROPOSED
            now = datetime.now(UTC)
            edges: list[RelationEdge] = []
            for point in matches:
                payload = point.get("payload") or {}
                if payload.get("status") != "active" or payload.get("record_type") != "knowledge":
                    continue
                try:
                    target_ref = EntityRef.from_payload(payload)
                except Exception:
                    continue
                if target_ref.key == source_ref.key:
                    continue
                target_id = UUID(str(point["id"]))
                evidence_ref = (
                    (EvidenceRef(record_type="episode", id=evidence_ids[0]),)
                    if evidence_ids
                    else ()
                )
                edges.append(
                    RelationEdge(
                        kind=RelationKind.SUPPORTS,
                        source=source_ref,
                        target=target_ref,
                        target_record_id=target_id,
                        evidence=evidence_ref,
                        status=status,
                        review_note="Automated dream semantic relation link",
                        valid_from=now,
                    )
                )
            if edges:
                return RelationBundle(schema_version=1, edges=tuple(edges))
        except Exception:
            return None
        return None

    def _domain_for(
        self,
        *,
        candidate: DreamCandidate,
        request: DreamReasoningRequest,
        evidence: list[EvidenceItem],
        domain_override: str | None = None,
    ) -> str | None:
        if domain_override is not None and domain_override.strip():
            return domain_override.strip()

        evidence_domains = {
            str(item.metadata["domain"]).strip()
            for item in evidence
            if item.metadata.get("domain") is not None and str(item.metadata["domain"]).strip()
        }
        if len(evidence_domains) > 1:
            return None
        if len(evidence_domains) == 1:
            return next(iter(evidence_domains))

        context_domains = {
            str(
                item.metadata.get("context", {}).get("legacy_domain")
                or item.metadata.get("context", {}).get("domain")
                or ""
            ).strip()
            for item in evidence
            if isinstance(item.metadata.get("context"), dict)
            and str(
                item.metadata.get("context", {}).get("legacy_domain")
                or item.metadata.get("context", {}).get("domain")
                or ""
            ).strip()
        }
        if len(context_domains) > 1:
            return None
        if len(context_domains) == 1:
            return next(iter(context_domains))

        candidate_domain = str(candidate.context.get("domain") or "").strip()
        if candidate_domain:
            return candidate_domain

        if self._default_domain:
            return self._default_domain

        return None

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
            str(item.metadata.get("verification") or "").strip().casefold() for item in evidence
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

        if request.focal_topics:
            return request.focal_topics[0]

        if topics:
            return sorted(topics)[0]

        raise ValueError("unable to resolve canonical topic for Dream candidate")
