# SPDX-License-Identifier: MPL-2.0
"""M6 orchestration, review, persistence, and bounded advisory integration."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any
from uuid import UUID

from cyberbrain.knowledge.evolution import EvolutionResult, KnowledgeEvolutionService
from cyberbrain.schemas.models import (
    IdentityTrust,
    KnowledgeRecordClass,
    KnowledgeStatus,
    Origin,
    RetentionDirective,
    Verification,
)
from cyberbrain.storage.base import PointRepository
from cyberbrain.tenancy import TrustedIdentityEvidence
from cyberbrain.working_memory.models import (
    TaskRelevance,
    WorkingMemoryCandidate,
    WorkingMemoryIdentity,
    WorkingMemoryItemKind,
)

from .engine import SelfModelHypothesisEngine
from .evidence import SelfModelEvidenceSet
from .models import (
    SelfModelHypothesis,
    SelfModelHypothesisKind,
    SelfModelReviewStatus,
)
from .readiness import (
    SelfModelReadinessEvaluator,
    SelfModelReadinessInput,
    SelfModelReadinessReport,
)

_SELF_MODEL_DOMAIN = "cognition"
_SELF_MODEL_TOPIC = "agent_self_model"
_SELF_MODEL_ENTITY_TYPE = "self_model_hypothesis"


class SelfModelService:
    """Complete M6 source pipeline; runtime authority remains explicit and bounded."""

    def __init__(
        self,
        *,
        readiness: SelfModelReadinessEvaluator | None = None,
        engine: SelfModelHypothesisEngine | None = None,
    ) -> None:
        self._readiness = readiness or SelfModelReadinessEvaluator()
        self._engine = engine or SelfModelHypothesisEngine()

    def analyze(
        self,
        evidence: SelfModelEvidenceSet,
        *,
        generated_at: datetime,
        trusted_identity: TrustedIdentityEvidence | None = None,
        require_runtime_identity: bool = False,
    ) -> tuple[SelfModelReadinessReport, tuple[SelfModelHypothesis, ...]]:
        readiness = self._readiness.evaluate(
            SelfModelReadinessInput(
                agent_id=evidence.agent_id,
                resolved_outcomes=evidence.resolved_pairs,
                trusted_resolved_outcomes=evidence.trusted_resolved_pairs,
                diversity=evidence.diversity,
                evidence_ids=evidence.evidence_ids,
                trusted_identity=trusted_identity,
                require_runtime_identity=require_runtime_identity,
                may_be_incomplete=evidence.may_be_incomplete,
            )
        )
        hypotheses = self._engine.generate(
            readiness=readiness,
            samples=evidence.samples,
            generated_at=generated_at,
        )
        return readiness, hypotheses

    @staticmethod
    def review(
        hypothesis: SelfModelHypothesis,
        *,
        status: SelfModelReviewStatus,
        reviewed_at: datetime,
    ) -> SelfModelHypothesis:
        return hypothesis.reviewed(status=status, reviewed_at=reviewed_at)


class SelfModelPersistence:
    """Persist only accepted M6 hypotheses inside canonical Knowledge Evolution."""

    def __init__(
        self,
        *,
        evolution: KnowledgeEvolutionService,
        repository: PointRepository,
        collection: str,
    ) -> None:
        self._evolution = evolution
        self._repository = repository
        self._collection = collection

    def persist(self, hypothesis: SelfModelHypothesis) -> EvolutionResult:
        if not hypothesis.accepted:
            raise ValueError("only accepted self-model hypotheses may be persisted")
        evidence_ids = [
            UUID(value)
            for value in dict.fromkeys(
                (*hypothesis.support_evidence_ids, *hypothesis.counterexample_evidence_ids)
            )
        ]
        entity_name = f"{hypothesis.agent_id}:{hypothesis.hypothesis_id}"
        extension = self._extension(hypothesis)
        force_evolution = self._metadata_revision_required(
            agent_id=hypothesis.agent_id,
            entity_name=entity_name,
            confidence=hypothesis.confidence,
            extension=extension,
        )
        return self._evolution.store(
            content=hypothesis.claim,
            summary=self._summary(hypothesis),
            record_class=KnowledgeRecordClass.SELF_MODEL_HYPOTHESIS,
            domain=_SELF_MODEL_DOMAIN,
            topic=_SELF_MODEL_TOPIC,
            entity_type=_SELF_MODEL_ENTITY_TYPE,
            entity_name=entity_name,
            agent=hypothesis.agent_id,
            identity_trust=IdentityTrust.SYSTEM_DERIVED,
            ordinary_recall=False,
            retention_directive=RetentionDirective.KEEP,
            change_reason="reviewed self-model hypothesis revision",
            verification=Verification.DERIVED,
            confidence=hypothesis.confidence,
            provenance_type="self_model_hypothesis",
            source="m6_self_model",
            evidence_ids=evidence_ids,
            origin=Origin.COGNITION,
            context={},
            extensions={"self_model": extension},
            force_evolution=force_evolution,
        )

    def _metadata_revision_required(
        self,
        *,
        agent_id: str,
        entity_name: str,
        confidence: float,
        extension: dict[str, Any],
    ) -> bool:
        existing = next(
            (
                row
                for row in self.load_active(agent_id=agent_id, limit=100)
                if str(row.get("entity_name") or "") == entity_name
            ),
            None,
        )
        if existing is None:
            return False
        current_extension = (existing.get("extensions") or {}).get("self_model") or {}
        semantic_keys = (
            "hypothesis_id",
            "kind",
            "scope_topic",
            "support_evidence_ids",
            "counterexample_evidence_ids",
            "sample_count",
            "diversity",
            "review_status",
            "reason_codes",
            "version",
        )
        current_semantics = {key: current_extension.get(key) for key in semantic_keys}
        target_semantics = {key: extension.get(key) for key in semantic_keys}
        if current_semantics != target_semantics:
            return True
        try:
            current_confidence = float(existing.get("confidence"))
        except (TypeError, ValueError):
            return True
        return abs(current_confidence - confidence) > 1e-12

    def load_active(self, *, agent_id: str, limit: int = 100) -> tuple[dict[str, Any], ...]:
        points = self._repository.scroll(
            self._collection,
            qdrant_filter={
                "must": [
                    {
                        "key": "record_class",
                        "match": {"value": KnowledgeRecordClass.SELF_MODEL_HYPOTHESIS.value},
                    },
                    {"key": "status", "match": {"value": KnowledgeStatus.ACTIVE.value}},
                    {"key": "agent", "match": {"value": agent_id}},
                ]
            },
            limit=limit,
        )
        return tuple(
            {"id": str(point["id"]), **dict(point.get("payload") or {})} for point in points
        )

    @staticmethod
    def _summary(hypothesis: SelfModelHypothesis) -> str:
        topic = hypothesis.scope_topic or "cross-topic"
        return (
            f"{hypothesis.kind.value} hypothesis for {hypothesis.agent_id}; "
            f"scope={topic}; confidence={hypothesis.confidence:.2f}; "
            f"samples={hypothesis.sample_count}"
        )

    @staticmethod
    def _extension(hypothesis: SelfModelHypothesis) -> dict[str, Any]:
        diversity = asdict(hypothesis.diversity)
        return {
            "hypothesis_id": hypothesis.hypothesis_id,
            "kind": hypothesis.kind.value,
            "scope_topic": hypothesis.scope_topic,
            "support_evidence_ids": list(hypothesis.support_evidence_ids),
            "counterexample_evidence_ids": list(hypothesis.counterexample_evidence_ids),
            "sample_count": hypothesis.sample_count,
            "diversity": diversity,
            "generated_at": hypothesis.generated_at.isoformat(),
            "review_status": hypothesis.review_status.value,
            "reviewed_at": hypothesis.reviewed_at.isoformat() if hypothesis.reviewed_at else None,
            "reason_codes": list(hypothesis.reason_codes),
            "version": hypothesis.version,
        }


class SelfModelWorkingMemoryAdapter:
    """Convert accepted hypotheses into informational M5 candidates only."""

    @staticmethod
    def candidate(
        hypothesis: SelfModelHypothesis,
        *,
        identity: WorkingMemoryIdentity,
        task_relevance: TaskRelevance,
    ) -> WorkingMemoryCandidate:
        if not hypothesis.accepted:
            raise ValueError(
                "self-model hypothesis must be accepted before Working Memory advisory use"
            )
        prefix = {
            SelfModelHypothesisKind.CAPABILITY: "Capability hypothesis",
            SelfModelHypothesisKind.LIMITATION: "Limitation hypothesis",
            SelfModelHypothesisKind.WORKFLOW_TENDENCY: "Workflow hypothesis",
            SelfModelHypothesisKind.STRATEGY_CONSTRAINT: "Strategy constraint hypothesis",
            SelfModelHypothesisKind.UNCERTAIN_CAPABILITY: "Uncertain capability hypothesis",
        }[hypothesis.kind]
        return WorkingMemoryCandidate(
            candidate_id=f"self-model:{hypothesis.hypothesis_id}",
            identity=identity,
            kind=WorkingMemoryItemKind.HYPOTHESIS,
            text=f"{prefix}: {hypothesis.claim}",
            task_relevance=task_relevance,
            reference_id=None,
            source_record_id=None,
        )
