# SPDX-License-Identifier: MPL-2.0
"""Active bounded M3→M7 runtime integration over already-visible candidates."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, OrderedDict
from datetime import UTC, datetime
from threading import RLock
from typing import Any
from uuid import UUID

from cyberbrain.concepts import (
    ConceptDiscoveryEngine,
    ConceptEvidence,
    ConceptEvidenceType,
    ConceptShadowRegistry,
)
from cyberbrain.core.metrics import MetricsRegistry
from cyberbrain.lifecycle import LifecycleDecisionKind, MemoryLifecycleService
from cyberbrain.salience import SalienceAdvisor, SalienceCandidate, SalienceInput
from cyberbrain.schemas.models import KnowledgeRecordClass, LifecycleState
from cyberbrain.self_model import (
    SelfModelPersistence,
    SelfModelReviewStatus,
    SelfModelService,
    extract_self_model_evidence,
)
from cyberbrain.storage.base import PointRepository
from cyberbrain.tenancy import TrustedIdentityEvidence
from cyberbrain.working_memory import (
    TaskRelevance,
    WorkingMemoryCandidate,
    WorkingMemoryIdentity,
    WorkingMemoryItemKind,
    WorkingMemoryService,
)

_WORD_RE = re.compile(r"[\w-]+", re.UNICODE)
_IMPORTANCE = {
    "critical": 1.0,
    "high": 0.85,
    "medium": 0.55,
    "normal": 0.45,
    "low": 0.2,
}


class CognitiveRuntimePath:
    """Server-owned event path activating M3–M7 without widening authorization.

    The path only receives rows that the existing retrieval/service layer already made visible.
    It never performs authorization itself and never widens filters or identity scope.
    """

    def __init__(
        self,
        *,
        repository: PointRepository,
        knowledge_collection: str,
        episodic_collection: str,
        metrics: MetricsRegistry,
        self_model: SelfModelService,
        self_model_persistence: SelfModelPersistence,
        memory_lifecycle: MemoryLifecycleService,
        enabled: bool = True,
        m6_auto_accept: bool = True,
        m7_actuation: bool = True,
        prefetch_multiplier: int = 3,
        concept_evidence_limit: int = 256,
    ) -> None:
        if prefetch_multiplier < 1:
            raise ValueError("cognition prefetch_multiplier must be >= 1")
        if concept_evidence_limit < 8:
            raise ValueError("cognition concept_evidence_limit must be >= 8")
        self.enabled = bool(enabled)
        self.m6_auto_accept = bool(m6_auto_accept)
        self.m7_actuation = bool(m7_actuation)
        self.prefetch_multiplier = int(prefetch_multiplier)
        self.concept_evidence_limit = int(concept_evidence_limit)
        self._repository = repository
        self.knowledge_collection = knowledge_collection
        self.episodic_collection = episodic_collection
        self.metrics = metrics
        self.self_model = self_model
        self.self_model_persistence = self_model_persistence
        self.memory_lifecycle = memory_lifecycle
        self.salience = SalienceAdvisor()
        self.concepts = ConceptDiscoveryEngine()
        self.concept_registry = ConceptShadowRegistry(metrics=metrics)
        self.working_memory = WorkingMemoryService(metrics=metrics)
        self._lock = RLock()
        self._concept_evidence: dict[str, OrderedDict[str, ConceptEvidence]] = {}

    def prefetch_limit(self, requested: int) -> int:
        if not self.enabled:
            return requested
        return min(50, max(requested, requested * self.prefetch_multiplier))

    def process_recall(
        self,
        rows: list[dict[str, Any]],
        *,
        query: str,
        kind: str,
        requested_limit: int,
        trusted_identity: TrustedIdentityEvidence | None = None,
        session_id: str | None = None,
        project: str | None = None,
        task_id: str | None = None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        if not self.enabled or not rows:
            return rows[:requested_limit]
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        scope_marker = self._scope_marker(trusted_identity, project=project)
        identity = WorkingMemoryIdentity(
            scope_marker=scope_marker,
            session_id=self._session_id(trusted_identity, explicit=session_id),
            task_id=(task_id or self._task_id(query)),
        )
        self.metrics.increment("cognition_active_recall_total")

        topics = Counter(str(row.get("topic") or "").strip().casefold() for row in rows)
        salience_inputs: dict[str, SalienceInput] = {}
        candidates: list[SalienceCandidate] = []
        row_by_candidate: dict[str, dict[str, Any]] = {}
        for row in rows:
            row_id = str(row.get("id") or "").strip()
            if not row_id:
                continue
            candidate_id = f"{kind}:{row_id}"
            signals = self._salience_input(
                row,
                now=instant,
                recurrence=topics.get(str(row.get("topic") or "").strip().casefold(), 0),
            )
            salience_inputs[candidate_id] = signals
            candidates.append(SalienceCandidate(candidate_id, scope_marker, signals))
            row_by_candidate[candidate_id] = row

        advisory = self.salience.assess(candidates)
        assessment_by_id = {item.candidate_id: item.assessment for item in advisory.assessments}
        self.metrics.increment("salience_active_assessments_total", len(assessment_by_id))

        concept_candidates = self._observe_concepts(
            rows,
            kind=kind,
            scope_marker=scope_marker,
        )
        concepts_by_topic: dict[str, list[str]] = {}
        for concept in concept_candidates:
            concepts_by_topic.setdefault(concept.topic.casefold(), []).append(
                concept.candidate_concept_id
            )

        wm_candidates: list[WorkingMemoryCandidate] = []
        row_relevance = {
            candidate_id: self._task_relevance(row, query)
            for candidate_id, row in row_by_candidate.items()
        }
        # Reserve two bounded M5 slots for M4/M6 advisory context. M3 still decides
        # which raw recall candidates are eligible for the remaining active slots.
        raw_slot_limit = max(1, self.working_memory.policy.max_items - 2)
        ranked_raw_ids = sorted(
            row_by_candidate,
            key=lambda candidate_id: (
                -row_relevance[candidate_id].score,
                -assessment_by_id[candidate_id].score,
                list(row_by_candidate).index(candidate_id),
            ),
        )[:raw_slot_limit]
        for candidate_id in ranked_raw_ids:
            row = row_by_candidate[candidate_id]
            row_id = str(row["id"])
            wm_candidates.append(
                WorkingMemoryCandidate(
                    candidate_id=candidate_id,
                    identity=identity,
                    kind=WorkingMemoryItemKind.SELECTED_MEMORY_REFERENCE,
                    text=self._row_text(row),
                    task_relevance=row_relevance[candidate_id],
                    salience=salience_inputs[candidate_id],
                    reference_id=row_id,
                    source_record_id=row_id,
                )
            )

        # Discovery/registry observes all candidates; M5 receives only a bounded advisory subset.
        for concept in concept_candidates[:8]:
            relevance = self._text_relevance(concept.topic, query, floor=0.25)
            wm_candidates.append(
                WorkingMemoryCandidate(
                    candidate_id=f"wm:{concept.candidate_concept_id}",
                    identity=identity,
                    kind=WorkingMemoryItemKind.CONCEPT_REFERENCE,
                    text=f"Concept candidate: {concept.label}",
                    task_relevance=TaskRelevance(relevance, ("concept_topic_overlap",)),
                    salience=SalienceInput(
                        recurrence=min(1.0, len(concept.supporting_evidence_ids) / 5.0),
                        consequence=min(1.0, concept.formation_confidence),
                    ),
                    reference_id=concept.candidate_concept_id,
                )
            )

        self_model_rows = self._active_self_model_rows(trusted_identity, query=query)
        for row in self_model_rows:
            wm_candidates.append(
                WorkingMemoryCandidate(
                    candidate_id=f"self-model:{row['id']}",
                    identity=identity,
                    kind=WorkingMemoryItemKind.HYPOTHESIS,
                    text=str(row.get("content") or row.get("summary") or "Self-model hypothesis"),
                    task_relevance=TaskRelevance(
                        self._text_relevance(
                            str(row.get("topic") or row.get("content") or ""),
                            query,
                            floor=0.3,
                        ),
                        ("accepted_self_model_advisory",),
                    ),
                    salience=SalienceInput(consequence=0.7, recurrence=0.5),
                    source_record_id=str(row["id"]),
                )
            )

        snapshot = self.working_memory.activate(identity, wm_candidates, now=instant)
        self.metrics.increment("working_memory_active_path_total")
        selected_candidate_ids = {item.candidate_id for item in snapshot.items}
        selected_row_ids = {
            item.source_record_id
            for item in snapshot.items
            if item.source_record_id and item.candidate_id in row_by_candidate
        }
        selected_order = [
            item.candidate_id for item in snapshot.items if item.candidate_id in row_by_candidate
        ]

        lifecycle_by_id: dict[str, str] = {}
        suppressed_ids: set[str] = set()
        if self.m7_actuation:
            for candidate_id, row in row_by_candidate.items():
                row_id = str(row["id"])
                selected = row_id in selected_row_ids
                assessment = assessment_by_id[candidate_id]
                linked = bool(concepts_by_topic.get(str(row.get("topic") or "").strip().casefold()))
                decision = self._apply_lifecycle_for_recall(
                    row,
                    kind=kind,
                    selected=selected,
                    salience_score=assessment.score,
                    concept_linked=linked,
                    now=instant,
                )
                if decision is not None:
                    lifecycle_by_id[row_id] = decision
                    if decision == LifecycleDecisionKind.SUPPRESS.value and not selected:
                        suppressed_ids.add(row_id)

        salience_order = list(advisory.priority_order)
        ordered_ids: list[str] = []
        for candidate_id in (*selected_order, *salience_order):
            if candidate_id not in ordered_ids:
                ordered_ids.append(candidate_id)
        ordered_rows = [
            row_by_candidate[candidate_id]
            for candidate_id in ordered_ids
            if str(row_by_candidate[candidate_id].get("id")) not in suppressed_ids
        ]
        returned = ordered_rows[:requested_limit]

        selected_concepts = [
            item.reference_id
            for item in snapshot.items
            if item.kind is WorkingMemoryItemKind.CONCEPT_REFERENCE and item.reference_id
        ]
        selected_self_model = [
            item.text for item in snapshot.items if item.kind is WorkingMemoryItemKind.HYPOTHESIS
        ]
        for rank, row in enumerate(returned):
            candidate_id = f"{kind}:{row['id']}"
            assessment = assessment_by_id.get(candidate_id)
            cognition = dict(row.get("_cognition") or {})
            cognition.update(
                {
                    "m3_salience_score": assessment.score if assessment else 0.0,
                    "m3_reason_codes": [
                        code.value for code in (assessment.reason_codes if assessment else ())
                    ],
                    "m5_working_memory_selected": candidate_id in selected_candidate_ids,
                    "m5_revision": snapshot.revision,
                    "m5_priority_rank": rank + 1,
                    "m7_decision": lifecycle_by_id.get(str(row.get("id"))),
                }
            )
            topic_key = str(row.get("topic") or "").strip().casefold()
            if concepts_by_topic.get(topic_key):
                cognition["m4_concept_ids"] = tuple(concepts_by_topic[topic_key])
            if rank == 0:
                if selected_concepts:
                    cognition["m4_active_concepts"] = tuple(selected_concepts[:5])
                if selected_self_model:
                    cognition["m6_self_model_advisories"] = tuple(selected_self_model[:3])
            row["_cognition"] = cognition
        return returned

    def process_exact_recall(
        self,
        row: dict[str, Any],
        *,
        kind: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not self.enabled or not row:
            return row
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        row_id = str(row.get("id") or "")
        if not row_id:
            return row
        if not self._lifecycle_eligible(row, kind=kind):
            return row
        try:
            point_id = UUID(row_id)
        except ValueError:
            return row
        collection = self.knowledge_collection if kind == "knowledge" else self.episodic_collection
        count = self.memory_lifecycle.record_access(
            collection=collection, point_id=point_id, now=instant
        )
        payload = dict(row)
        payload["access_count"] = count
        payload["last_accessed_at"] = instant.isoformat()
        decision = self.memory_lifecycle.evaluate_payload(
            point_id=row_id,
            payload=payload,
            now=instant,
            salience_score=1.0,
            explicit_relevance=True,
        )
        if self.m7_actuation and decision.decision is LifecycleDecisionKind.REACTIVATE:
            self.memory_lifecycle.apply_decision(
                collection=collection,
                point_id=point_id,
                decision=decision,
                now=instant,
            )
            row["lifecycle_state"] = LifecycleState.ACTIVE.value
            row["ordinary_recall"] = True
        row["access_count"] = count
        row["last_accessed_at"] = instant.isoformat()
        row.setdefault("_cognition", {})["m7_decision"] = decision.decision.value
        self.metrics.increment("lifecycle_active_exact_recall_total")
        return row

    def observe_store(
        self,
        row: dict[str, Any],
        *,
        kind: str,
        trusted_identity: TrustedIdentityEvidence | None = None,
    ) -> None:
        if not self.enabled:
            return
        scope = self._scope_marker(trusted_identity, project=str(row.get("project") or "") or None)
        self._remember_concept_evidence(row, kind=kind, scope_marker=scope)
        self.metrics.increment("cognition_active_store_observed_total")

    def run_self_model(
        self,
        *,
        trusted_identity: TrustedIdentityEvidence | None,
        generated_at: datetime | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "generated": 0, "persisted": 0}
        agent = self._single_agent(trusted_identity)
        if agent is None:
            self.metrics.increment("self_model_active_identity_missing_total")
            return {"status": "insufficient_evidence", "generated": 0, "persisted": 0}
        points = self._repository.scroll(
            self.episodic_collection,
            qdrant_filter={"must": [{"key": "agent", "match": {"value": agent}}]},
            limit=10_000,
        )
        evidence = extract_self_model_evidence(
            points, agent_id=agent, may_be_incomplete=len(points) >= 10_000
        )
        readiness, hypotheses = self.self_model.analyze(
            evidence,
            generated_at=(generated_at or datetime.now(UTC)).astimezone(UTC),
            trusted_identity=trusted_identity,
            require_runtime_identity=True,
        )
        self.metrics.increment("self_model_active_runs_total")
        self.metrics.observe("self_model_active_resolved_outcomes", readiness.resolved_outcomes)
        if not readiness.ready:
            self.metrics.increment("self_model_active_insufficient_evidence_total")
            return {
                "status": readiness.status.value,
                "generated": 0,
                "persisted": 0,
                "trusted_resolved_outcomes": readiness.trusted_resolved_outcomes,
            }

        persisted = 0
        if self.m6_auto_accept:
            reviewed_at = (generated_at or datetime.now(UTC)).astimezone(UTC)
            for hypothesis in hypotheses:
                accepted = self.self_model.review(
                    hypothesis,
                    status=SelfModelReviewStatus.ACCEPTED,
                    reviewed_at=reviewed_at,
                )
                self.self_model_persistence.persist(accepted)
                persisted += 1
            self.metrics.increment("self_model_active_auto_accepted_total", persisted)
        return {
            "status": readiness.status.value,
            "generated": len(hypotheses),
            "persisted": persisted,
            "trusted_resolved_outcomes": readiness.trusted_resolved_outcomes,
        }

    def _observe_concepts(
        self,
        rows: list[dict[str, Any]],
        *,
        kind: str,
        scope_marker: str,
    ) -> tuple[Any, ...]:
        for row in rows:
            self._remember_concept_evidence(row, kind=kind, scope_marker=scope_marker)
        with self._lock:
            evidence = tuple(self._concept_evidence.get(scope_marker, {}).values())
            concepts = self.concepts.discover(evidence)
            self.concept_registry.observe(concepts)
        self.metrics.increment("concept_active_discovery_runs_total")
        self.metrics.increment("concept_active_candidates_total", len(concepts))
        return concepts

    def _remember_concept_evidence(
        self, row: dict[str, Any], *, kind: str, scope_marker: str
    ) -> None:
        row_id = str(row.get("id") or "").strip()
        topic = str(row.get("topic") or "").strip()
        if not row_id or not topic:
            return
        domain = str(row.get("domain") or row.get("project") or kind).strip() or kind
        cognition = row.get("context") or {}
        counterexample = False
        if isinstance(cognition, dict):
            c = cognition.get("cognition")
            counterexample = isinstance(c, dict) and c.get("assessment") == "contradicted"
        evidence = ConceptEvidence(
            evidence_id=f"{kind}:{row_id}",
            record_type=(
                ConceptEvidenceType.KNOWLEDGE
                if kind == "knowledge"
                else ConceptEvidenceType.EPISODE
            ),
            scope_marker=scope_marker,
            domain=domain,
            topic=topic,
            project=str(row.get("project") or "").strip() or None,
            entity_type=str(row.get("entity_type") or "").strip() or None,
            entity_name=str(row.get("entity_name") or "").strip() or None,
            session_id=str(row.get("session_id") or "").strip() or None,
            source=str(row.get("source") or "").strip() or None,
            verification=str(row.get("verification") or "").strip() or None,
            counterexample=counterexample,
        )
        with self._lock:
            bucket = self._concept_evidence.setdefault(scope_marker, OrderedDict())
            bucket[evidence.evidence_id] = evidence
            bucket.move_to_end(evidence.evidence_id)
            while len(bucket) > self.concept_evidence_limit:
                bucket.popitem(last=False)

    def _apply_lifecycle_for_recall(
        self,
        row: dict[str, Any],
        *,
        kind: str,
        selected: bool,
        salience_score: float,
        concept_linked: bool,
        now: datetime,
    ) -> str | None:
        if not self._lifecycle_eligible(row, kind=kind):
            return None
        row_id = str(row.get("id") or "")
        try:
            point_id = UUID(row_id)
        except ValueError:
            return None
        collection = self.knowledge_collection if kind == "knowledge" else self.episodic_collection
        payload = dict(row)
        if selected:
            try:
                count = self.memory_lifecycle.record_access(
                    collection=collection, point_id=point_id, now=now
                )
                payload["access_count"] = count
                payload["last_accessed_at"] = now.isoformat()
                row["access_count"] = count
                row["last_accessed_at"] = now.isoformat()
            except KeyError:
                return None
        try:
            decision = self.memory_lifecycle.evaluate_payload(
                point_id=row_id,
                payload=payload,
                now=now,
                salience_score=salience_score,
                concept_linked=concept_linked,
                unresolved=self._unresolved(row),
                explicit_relevance=selected,
            )
        except ValueError:
            self.metrics.increment("lifecycle_active_evaluation_errors_total")
            return None
        if self.m7_actuation and decision.decision in {
            LifecycleDecisionKind.SUPPRESS,
            LifecycleDecisionKind.REACTIVATE,
        }:
            self.memory_lifecycle.apply_decision(
                collection=collection,
                point_id=point_id,
                decision=decision,
                now=now,
            )
            self.metrics.increment(f"lifecycle_active_{decision.decision.value}_total")
        else:
            self.metrics.increment("lifecycle_active_keep_total")
        return decision.decision.value

    def _active_self_model_rows(
        self,
        trusted_identity: TrustedIdentityEvidence | None,
        *,
        query: str,
    ) -> tuple[dict[str, Any], ...]:
        agent = self._single_agent(trusted_identity)
        if agent is None:
            return ()
        rows = self.self_model_persistence.load_active(agent_id=agent, limit=25)
        ranked = sorted(
            rows,
            key=lambda row: self._text_relevance(
                str(row.get("content") or row.get("summary") or ""), query, floor=0.0
            ),
            reverse=True,
        )
        return tuple(ranked[:5])

    @staticmethod
    def _single_agent(identity: TrustedIdentityEvidence | None) -> str | None:
        if identity is None or len(identity.scope.agent) != 1:
            return None
        return next(iter(identity.scope.agent))

    @staticmethod
    def _scope_marker(identity: TrustedIdentityEvidence | None, *, project: str | None) -> str:
        if identity is None:
            return f"single_owner|project={project or '-'}"
        parts = []
        for key, values in identity.scope.as_dict().items():
            parts.append(f"{key}={','.join(values)}")
        if project and "project=" not in "|".join(parts):
            parts.append(f"project={project}")
        return "trusted|" + "|".join(parts or ["single_owner"])

    @staticmethod
    def _session_id(identity: TrustedIdentityEvidence | None, *, explicit: str | None) -> str:
        if explicit and explicit.strip():
            return explicit.strip()
        if identity is not None and len(identity.scope.session) == 1:
            return next(iter(identity.scope.session))
        agent = CognitiveRuntimePath._single_agent(identity) or "single-owner"
        return f"runtime:{agent}"

    @staticmethod
    def _task_id(query: str) -> str:
        return "query:" + hashlib.sha256(query.strip().casefold().encode()).hexdigest()[:16]

    @staticmethod
    def _row_text(row: dict[str, Any]) -> str:
        return str(
            row.get("recall_text")
            or row.get("summary")
            or row.get("content")
            or row.get("expected_outcome")
            or row.get("topic")
            or "memory"
        ).strip()

    @staticmethod
    def _task_relevance(row: dict[str, Any], query: str) -> TaskRelevance:
        raw = row.get("score")
        vector = float(raw) if isinstance(raw, int | float) and math.isfinite(float(raw)) else 0.5
        vector = min(1.0, max(0.0, vector))
        # Quantize semantic relevance so Salience can materially order near-neighbor rows.
        semantic = round(vector * 5.0) / 5.0
        lexical = CognitiveRuntimePath._text_relevance(
            CognitiveRuntimePath._row_text(row), query, floor=0.0
        )
        score = min(1.0, max(semantic, lexical))
        reasons = ["semantic_relevance"]
        if lexical > 0:
            reasons.append("lexical_overlap")
        return TaskRelevance(score, tuple(reasons))

    @staticmethod
    def _text_relevance(text: str, query: str, *, floor: float) -> float:
        query = query.replace("_", " ")
        text = text.replace("_", " ")
        q = {token.casefold() for token in _WORD_RE.findall(query) if len(token) > 2}
        t = {token.casefold() for token in _WORD_RE.findall(text) if len(token) > 2}
        if not q or not t:
            return floor
        overlap = len(q & t) / len(q)
        return min(1.0, max(floor, overlap))

    @staticmethod
    def _unresolved(row: dict[str, Any]) -> bool:
        context = row.get("context")
        if isinstance(context, dict):
            cognition = context.get("cognition")
            if isinstance(cognition, dict):
                if cognition.get("unresolved") is True:
                    return True
                if cognition.get("kind") == "prediction" and not cognition.get("resolved"):
                    return True
        return str(row.get("dream_status") or "") == "pending"

    @staticmethod
    def _salience_input(row: dict[str, Any], *, now: datetime, recurrence: int) -> SalienceInput:
        context = row.get("context")
        cognition = context.get("cognition") if isinstance(context, dict) else None
        prediction_error = None
        contradiction = None
        unresolved = None
        if isinstance(cognition, dict):
            raw_error = cognition.get("confidence_weighted_error")
            if isinstance(raw_error, int | float):
                prediction_error = min(1.0, max(0.0, float(raw_error)))
            contradiction = 1.0 if cognition.get("assessment") == "contradicted" else None
            if cognition.get("unresolved") is True or cognition.get("kind") == "prediction":
                unresolved = 1.0
        if unresolved is None and str(row.get("dream_status") or "") == "pending":
            unresolved = 0.7
        importance = _IMPORTANCE.get(str(row.get("importance") or "").casefold())
        recency = CognitiveRuntimePath._recency(row, now=now)
        return SalienceInput(
            prediction_error=prediction_error,
            unresolvedness=unresolved,
            contradiction=contradiction,
            novelty=None,
            recurrence=min(1.0, recurrence / 5.0) if recurrence else None,
            consequence=importance,
            user_emphasis=importance,
            recency=recency,
        )

    @staticmethod
    def _recency(row: dict[str, Any], *, now: datetime) -> float | None:
        for key in ("updated_at", "event_time", "created_at"):
            value = row.get(key)
            if value is None:
                continue
            try:
                parsed = (
                    value
                    if isinstance(value, datetime)
                    else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                )
            except ValueError:
                continue
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                continue
            days = max(0.0, (now - parsed.astimezone(UTC)).total_seconds() / 86400.0)
            if days <= 1:
                return 1.0
            if days <= 7:
                return 0.8
            if days <= 30:
                return 0.6
            if days <= 90:
                return 0.35
            if days <= 180:
                return 0.15
            return 0.0
        return None

    @staticmethod
    def _lifecycle_eligible(row: dict[str, Any], *, kind: str) -> bool:
        if kind != "knowledge":
            return True
        record_class = str(row.get("record_class") or KnowledgeRecordClass.KNOWLEDGE.value)
        return record_class == KnowledgeRecordClass.KNOWLEDGE.value
